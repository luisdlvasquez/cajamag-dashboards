"""
Inserta (o actualiza) el enriquecimiento client-side de GESTIONES y EMPRESAS
en un archivo HTML de dashboard/tablero.

Por que existe este script: Bitrix (bitrix.cajamag.com.co) bloquea las llamadas
salientes que vienen de servidores en la nube (Supabase Edge Functions incluido),
asi que el enriquecimiento real (traer categoria/etapa/responsable desde Bitrix
REST) solo puede hacerse desde un navegador dentro de la red de la empresa.
Este script inyecta ese codigo directamente en el Tablero TV y los dashboards,
para que se ejecute en segundo plano cada vez que alguien los tiene abiertos.

Que hace en segundo plano (sin UI visible):
  1. Gestiones: sondea bitrix_gestiones_eventos (procesado=false), trae cada
     negociacion via crm.deal.get, y si CATEGORY_ID=24 (Promocion, Mantenimiento
     y Afiliaciones) y STAGE_ID esta en {C24:UC_OCS434 (EJECUCION EVENTO),
     C24:WON (NEGOCIACION)} la marca como 'gestion realizada'. C24:LOSE ("-")
     y las demas etapas NO cuentan (asi lo confirmo el usuario: esa etapa no
     deberia usarse). Actualiza la fila con procesado=true + los datos.
     Ademas, para CATEGORY_ID=24 tambien captura el "medio" (Tipo de actividad:
     Llamada/Visita presencial/WhatsApp/Correo electronico/Reunion virtual,
     campo UF_CRM_1740085404851) y el "evento" (Tipo de evento: Empresa
     contactada por primera vez/Gestion fallida/etc, campo
     UF_CRM_1740428574274, es multiselect y se guarda unido con " / "), el NIT
     de la empresa vinculada (campo UF_CRM_1679587096910 en crm.company) y el
     comentario (COMMENTS) — cada "gestion" en Bitrix es literalmente un
     negocio de esta categoria, con estos mismos campos que usa el reporte
     manual "Gestiones CER", asi que esto permite tener el conteo de
     llamadas/visitas/whatsapp/correos en vivo sin depender del Excel manual.
  2. Empresas: sondea bitrix_empresas_eventos (procesado=false), trae cada
     compania via crm.company.get, y compara su ASSIGNED_BY_ID contra el ultimo
     valor guardado en empresas_estado. Si cambio, inserta una fila en
     empresas_cambios_asesor (log de cambios de responsable) y actualiza el
     estado. Si es la primera vez que se ve esa empresa, solo se guarda el
     estado inicial (no se considera "cambio").

Es idempotente (usa un marcador HTML) y no muestra nada en pantalla; solo
alimenta las tablas de Supabase para que el resto del dashboard (o futuros
paneles) puedan leerlas.

Uso manual:
    python3 webhook_enrich_widget.py Dashboard_Operativo_CER.html Dashboard_Gerencial_CER.html Tablero_TV_Asesores_CER.html
"""
import sys

MARKER_START = "<!-- CER-WEBHOOK-ENRICH v1 -->"
MARKER_END = "<!-- /CER-WEBHOOK-ENRICH v1 -->"

SUPA_URL = "https://nzmnzmnozbeqttofbmlf.supabase.co"
SUPA_ANON = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im56bW56bW5vemJlcXR0b2ZibWxmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk2NTAzMjQsImV4cCI6MjA5NTIyNjMyNH0.r3hrXsazoJK_xUWTsskEgjQ40Xhg60_0YaGvWs1VXP8")
BITRIX_REST_URL = "https://bitrix.cajamag.com.co/rest/24371/jptcd95wxx2lruif/"

SNIPPET = """<!-- CER-WEBHOOK-ENRICH v1 -->
<script>
(function(){
  var SUPA_URL = '__SUPA_URL__';
  var SUPA_ANON = '__SUPA_ANON__';
  var BITRIX_REST_URL = '__BITRIX_REST_URL__';

  // Etapas de categoria 24 (Promocion, Mantenimiento y Afiliaciones) que cuentan
  // como "gestion realizada": EJECUCION EVENTO o cierre en NEGOCIACION.
  // C24:LOSE ("-") NO cuenta (confirmado por el usuario: no deberia usarse).
  var GESTION_REALIZADA_STAGES = ['C24:UC_OCS434', 'C24:WON'];
  var CATEGORIA_GESTIONES = 24;

  // Campos personalizados de la categoria 24 (confirmados via crm.deal.fields
  // el 25-ago-2026): "Tipo de actividad (V)" = medio, "Tipo de evento (V)" =
  // gestion. El NIT vive en la Compania vinculada, no en el negocio.
  var CAMPO_MEDIO = 'UF_CRM_1740085404851';
  var CAMPO_EVENTO = 'UF_CRM_1740428574274';
  var CAMPO_NIT_EMPRESA = 'UF_CRM_1679587096910';

  function bitrixCall(method, params){
    var qs = new URLSearchParams(params || {}).toString();
    return fetch(BITRIX_REST_URL + method + '.json' + (qs ? '?' + qs : ''))
      .then(function(r){ return r.json(); })
      .then(function(d){ return d && d.result ? d.result : null; })
      .catch(function(){ return null; });
  }

  // Mapa ID->VALUE de los items de un campo tipo enumeracion (lista), para
  // traducir los IDs numericos que trae crm.deal.get a texto legible. Se
  // resuelve una sola vez (cacheado) via crm.deal.fields.
  var dealFieldsCache = null;
  function getDealFieldItemsMap(fieldCode){
    var fetchFields = dealFieldsCache || (dealFieldsCache = bitrixCall('crm.deal.fields', {}));
    return fetchFields.then(function(fields){
      var f = fields && fields[fieldCode];
      var map = {};
      if(f && Array.isArray(f.items)){
        f.items.forEach(function(it){ map[it.ID] = it.VALUE; });
      }
      return map;
    });
  }
  function traducirEnum(valor, map){
    if(valor == null) return null;
    if(Array.isArray(valor)) return valor.map(function(v){ return map[v] || map[String(v)] || null; }).filter(Boolean).join(' / ') || null;
    return map[valor] || map[String(valor)] || null;
  }

  function sb(path, opts){
    opts = opts || {};
    opts.headers = Object.assign({
      apikey: SUPA_ANON, Authorization: 'Bearer ' + SUPA_ANON,
      'content-type': 'application/json'
    }, opts.headers || {});
    return fetch(SUPA_URL + '/rest/v1/' + path, opts).then(function(r){
      return r.status === 204 ? null : r.json().catch(function(){ return null; });
    });
  }

  // ---------------- Gestiones ----------------
  function procesarGestion(row){
    return bitrixCall('crm.deal.get', { ID: row.deal_id }).then(function(deal){
      if(!deal){
        // Negocio no encontrado (borrado, o error de red) -> marcar procesado igual
        return sb('bitrix_gestiones_eventos?id=eq.' + row.id, {
          method: 'PATCH', body: JSON.stringify({ procesado: true, enriquecido_en: new Date().toISOString() })
        });
      }
      var categoryId = Number(deal.CATEGORY_ID);
      var stageId = deal.STAGE_ID;
      var patch = {
        procesado: true,
        category_id: categoryId,
        stage_id: stageId,
        titulo: deal.TITLE || null,
        asesor_id: deal.ASSIGNED_BY_ID ? Number(deal.ASSIGNED_BY_ID) : null,
        fecha_evento: new Date().toISOString(),
        enriquecido_en: new Date().toISOString()
      };
      if(categoryId === CATEGORIA_GESTIONES && GESTION_REALIZADA_STAGES.indexOf(stageId) !== -1){
        patch.tipo = (stageId === 'C24:WON') ? 'negociacion' : 'ejecucion';
      }
      patch.comentario = deal.COMMENTS || null;
      patch.fecha_gestion = (deal.BEGINDATE || deal.DATE_CREATE || '').slice(0, 10) || null;

      // Traer nombre de empresa y asesor (best-effort, no bloquea si falla)
      var lookups = [];
      if(deal.COMPANY_ID){
        lookups.push(bitrixCall('crm.company.get', { ID: deal.COMPANY_ID }).then(function(c){
          if(c && c.TITLE) patch.empresa = c.TITLE;
          if(c && c[CAMPO_NIT_EMPRESA]) patch.nit = String(c[CAMPO_NIT_EMPRESA]);
        }));
      }
      if(deal.ASSIGNED_BY_ID){
        lookups.push(bitrixCall('user.get', { ID: deal.ASSIGNED_BY_ID }).then(function(u){
          var user = Array.isArray(u) ? u[0] : u;
          if(user) patch.asesor = ((user.NAME||'') + ' ' + (user.LAST_NAME||'')).trim();
        }));
      }
      // Medio (Tipo de actividad) y evento (Tipo de evento), solo para la
      // categoria de gestiones — son campos de lista, hay que traducir el/los
      // ID(s) numericos a texto legible via el mapa de items del campo.
      if(categoryId === CATEGORIA_GESTIONES){
        lookups.push(getDealFieldItemsMap(CAMPO_MEDIO).then(function(map){
          patch.medio = traducirEnum(deal[CAMPO_MEDIO], map);
        }));
        lookups.push(getDealFieldItemsMap(CAMPO_EVENTO).then(function(map){
          patch.evento = traducirEnum(deal[CAMPO_EVENTO], map);
        }));
      }
      return Promise.all(lookups).then(function(){
        return sb('bitrix_gestiones_eventos?id=eq.' + row.id, { method: 'PATCH', body: JSON.stringify(patch) });
      });
    });
  }

  function cicloGestiones(){
    sb('bitrix_gestiones_eventos?procesado=eq.false&order=creado_en.asc&limit=25').then(function(rows){
      if(!Array.isArray(rows) || !rows.length) return;
      rows.reduce(function(p, row){ return p.then(function(){ return procesarGestion(row); }); }, Promise.resolve());
    }).catch(function(e){ console.error('gestiones enrich error', e); });
  }

  // ---------------- Empresas (deteccion de cambio de asesor) ----------------
  function procesarEmpresa(row){
    return bitrixCall('crm.company.get', { ID: row.company_id }).then(function(company){
      if(!company){
        return sb('bitrix_empresas_eventos?id=eq.' + row.id, { method: 'PATCH', body: JSON.stringify({ procesado: true }) });
      }
      var nuevoAsesorId = company.ASSIGNED_BY_ID ? Number(company.ASSIGNED_BY_ID) : null;
      var nombreEmpresa = company.TITLE || null;

      return sb('empresas_estado?company_id=eq.' + row.company_id + '&select=*').then(function(estadoRows){
        var previo = Array.isArray(estadoRows) && estadoRows.length ? estadoRows[0] : null;

        function guardarEstadoYMarcar(nombreAsesorNuevo){
          var upsert = sb('empresas_estado', {
            method: 'POST',
            headers: { Prefer: 'resolution=merge-duplicates' },
            body: JSON.stringify([{
              company_id: Number(row.company_id),
              nombre_empresa: nombreEmpresa,
              asesor_id: nuevoAsesorId,
              asesor_nombre: nombreAsesorNuevo || null,
              actualizado_en: new Date().toISOString()
            }])
          });
          var marcar = sb('bitrix_empresas_eventos?id=eq.' + row.id, { method: 'PATCH', body: JSON.stringify({ procesado: true }) });
          return Promise.all([upsert, marcar]);
        }

        function conNombreAsesor(cb){
          if(!nuevoAsesorId) return cb(null);
          bitrixCall('user.get', { ID: nuevoAsesorId }).then(function(u){
            var user = Array.isArray(u) ? u[0] : u;
            cb(user ? ((user.NAME||'') + ' ' + (user.LAST_NAME||'')).trim() : null);
          });
        }

        // Primera vez que vemos esta empresa: solo se guarda el estado inicial, no es "cambio"
        if(!previo){
          return new Promise(function(resolve){ conNombreAsesor(function(nombre){ resolve(guardarEstadoYMarcar(nombre)); }); });
        }

        // Sin cambio real de responsable -> solo refrescar estado
        if (previo.asesor_id === nuevoAsesorId) {
          return new Promise(function(resolve){ conNombreAsesor(function(nombre){ resolve(guardarEstadoYMarcar(nombre)); }); });
        }

        // Cambio real de asesor detectado -> loguear + actualizar estado
        return new Promise(function(resolve){
          conNombreAsesor(function(nombre){
            var log = sb('empresas_cambios_asesor', {
              method: 'POST',
              body: JSON.stringify([{
                company_id: Number(row.company_id),
                nombre_empresa: nombreEmpresa,
                asesor_anterior_id: previo.asesor_id,
                asesor_anterior_nombre: previo.asesor_nombre,
                asesor_nuevo_id: nuevoAsesorId,
                asesor_nuevo_nombre: nombre,
                detectado_en: new Date().toISOString()
              }])
            });
            resolve(Promise.all([log, guardarEstadoYMarcar(nombre)]));
          });
        });
      });
    });
  }

  function cicloEmpresas(){
    sb('bitrix_empresas_eventos?procesado=eq.false&order=creado_en.asc&limit=25').then(function(rows){
      if(!Array.isArray(rows) || !rows.length) return;
      rows.reduce(function(p, row){ return p.then(function(){ return procesarEmpresa(row); }); }, Promise.resolve());
    }).catch(function(e){ console.error('empresas enrich error', e); });
  }

  function ciclo(){ cicloGestiones(); cicloEmpresas(); }
  ciclo();
  setInterval(ciclo, 45000);
})();
</script>
<!-- /CER-WEBHOOK-ENRICH v1 -->"""

SNIPPET = (SNIPPET.replace("__SUPA_URL__", SUPA_URL)
                   .replace("__SUPA_ANON__", SUPA_ANON)
                   .replace("__BITRIX_REST_URL__", BITRIX_REST_URL))


def inject(path):
    with open(path, encoding="utf-8") as f:
        html = f.read()

    if MARKER_START in html and MARKER_END in html:
        i = html.index(MARKER_START)
        j = html.index(MARKER_END) + len(MARKER_END)
        html = html[:i] + html[j:]

    if "</body>" in html:
        idx = html.rindex("</body>")
        html = html[:idx] + SNIPPET + "\n" + html[idx:]
    else:
        html += "\n" + SNIPPET

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print("enriquecimiento webhook (gestiones+empresas) aplicado a", path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 webhook_enrich_widget.py archivo1.html [archivo2.html ...]")
        sys.exit(1)
    for p in sys.argv[1:]:
        inject(p)
