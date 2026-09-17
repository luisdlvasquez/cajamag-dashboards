import glob, os, sys
import json, re

_env_base = os.environ.get("PIPELINE_BASE_DIR")
if _env_base:
    SRC = f"{_env_base}/_automation/Dashboard_Master_DATA.html"
    OUT = f"{os.environ.get('PIPELINE_OUT_DIR', _env_base + '/_out')}/Dashboard_Operativo_CER.html"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
else:
    _candidates = glob.glob("/sessions/*/mnt/Trabajando Juntos")
    if not _candidates:
        print("ERROR: no se encontro la carpeta 'Trabajando Juntos' montada bajo /sessions/*/mnt/")
        sys.exit(1)
    _mnt = os.path.dirname(_candidates[0])
    SRC = f"{_candidates[0]}/CAJAMAG/02_DASHBOARDS/_automation/Dashboard_Master_DATA.html"
    OUT = f"{_mnt}/outputs/Dashboard_Operativo_CER.html"

html = open(SRC, encoding='utf-8').read()

# ---------- 1. Parse DATA ----------
d_start = html.index('const DATA = ') + len('const DATA = ')
d_end = html.index('function fmt(n)')
blob = html[d_start:d_end].strip()
assert blob.endswith(';')
blob = blob[:-1]
DATA = json.loads(blob)

# 26-ago-2026, a pedido de Luis: el Operativo pasa de tener solo 2 secciones
# (Historia + Ultimos Hechos) a tener las MISMAS 6 que existen en el archivo
# maestro (Resumen, Gestion, Empresas, Ventas, Historia, Ultimos Hechos), para
# que quede "alineado" con lo que ya se ve resumido en el Tablero TV pero con
# el detalle filtrable/exportable a Excel que el Tablero no tiene (bases de
# datos de empresas, gestiones y ventas). Se excluye 'analisis_cruzado' porque
# es exclusivo del Gerencial/Analitico (el embudo tiene un bug de calculo
# pendiente de corregir, señalado en el informe del 18-ago) y no fue pedido
# aqui. A diferencia del Gerencial, el Operativo SI incluye 'historia_asesor'
# (su ventaja propia) y NO lleva password.
data_min = {k: v for k, v in DATA.items() if k != 'analisis_cruzado'}

# 2-sep-2026, a pedido de Luis ("una cosita que se me olvidaba... esto solo en
# el dashboard operativo, en el gerencial no, la meta de ventas un 25% mas
# alto"): se sube la meta de ventas (equipo, zona, asesor, mensual y
# acumulada) un 25% SOLO en este build (Operativo). El Gerencial (build_gerencial.py)
# lee el mismo master sin este parche, asi que conserva la meta original.
# Se recalculan tambien los % de cumplimiento que dependian de esa meta para
# que no queden desincronizados con el nuevo denominador.
_META_FACTOR = 1.25
_v = data_min['ventas']
_v['meta_contractual_mensual'] = round(_v['meta_contractual_mensual'] * _META_FACTOR, 2)
_v['meta_contractual_zona_mensual'] = {k: round(val * _META_FACTOR, 2) for k, val in _v['meta_contractual_zona_mensual'].items()}
_v['meta_asesores_zona_mensual'] = {k: round(val * _META_FACTOR, 2) for k, val in _v['meta_asesores_zona_mensual'].items()}
for _t in _v['tendencia']:
    _t['meta'] = round(_t['meta'] * _META_FACTOR, 2)
for _r in _v['ranking']:
    if _r.get('meta_mensual') is not None:
        _r['meta_mensual'] = round(_r['meta_mensual'] * _META_FACTOR, 2)
    if _r.get('meta_acumulada_5m') is not None:
        _r['meta_acumulada_5m'] = round(_r['meta_acumulada_5m'] * _META_FACTOR, 2)
        _r['cumpl_acumulado'] = round(_r['total_acumulado'] / _r['meta_acumulada_5m'] * 100, 1) if _r['meta_acumulada_5m'] else 0
_v['meta_asesores_mensual_total'] = round(sum(_r['meta_mensual'] for _r in _v['ranking'] if _r.get('meta_mensual') is not None), 2)
_v['meta_ejecutado_5m'] = round(_v['meta_ejecutado_5m'] * _META_FACTOR, 2)
_v['cumpl_ejecutado_5m_pct'] = round(_v['total_ejecutado_5m'] / _v['meta_ejecutado_5m'] * 100, 1) if _v['meta_ejecutado_5m'] else 0
print(f"Meta de ventas +{int((_META_FACTOR-1)*100)}% aplicada SOLO en Operativo -- meta_contractual_mensual: {_v['meta_contractual_mensual']:,.0f}")

new_data_json = json.dumps(data_min, ensure_ascii=False, separators=(',', ':'))
print("Original DATA blob chars:", len(blob), "-> operativo minimizado:", len(new_data_json))

# ---------- 2. Head/CSS: unchanged (up to <body>) ----------
head = html[:html.index('<body>')]

# ---------- 3. Body markup ----------
# El nav del maestro ya trae los 6 items (Resumen/Gestion/Empresas/Ventas +
# separador + Historia/Ultimos Hechos) con Resumen activo por defecto -> no
# hace falta tocarlo.
body_start = html.index('<body>')
main_close = html.index('</section>\n  </main>') + len('</section>')
script_open = html.index('<script>', main_close)

body_full = html[body_start:main_close] + "\n  </main>\n</div>\n\n"

new_header = body_full.replace(
    '<span class="opt-tag">Análisis Cruzado — Segmentación completa</span>',
    '<span class="opt-tag">Vista Operativa — Gestión, Empresas, Ventas e Historia</span>'
)
body_new = new_header

# ---------- 4. Script tail ----------
script_full = html[script_open + len('<script>'): html.rindex('</script>')]

def cut(s, start_marker, end_marker):
    i = s.index(start_marker)
    j = s.index(end_marker, i)
    return s[i:j], i, j

helpers, _, _ = cut(script_full, 'function fmt(n){', '// ---- Nav ----')
nav_js, _, _ = cut(script_full, '// ---- Nav ----', '// ================= HEALTH STRIP =================')
health_js, _, _ = cut(script_full, '// ================= HEALTH STRIP =================', '// ================= RESUMEN =================')
resumen_js, _, _ = cut(script_full, '// ================= RESUMEN =================', '// ================= GESTIÓN =================')
gestion_js, _, _ = cut(script_full, '// ================= GESTIÓN =================', '// ================= EMPRESAS =================')
empresas_js, _, _ = cut(script_full, '// ================= EMPRESAS =================', '// ================= VENTAS =================')
ventas_js, _, _ = cut(script_full, '// ================= VENTAS =================', '// ================= HISTORIA COMERCIAL DEL ASESOR =================')
historia_js, _, _ = cut(script_full, '// ================= HISTORIA COMERCIAL DEL ASESOR =================',
                         '// ================= RESUMEN: cumplimiento vs metas contractuales =================')
resumen_cumpl_js, _, _ = cut(script_full, '// ================= RESUMEN: cumplimiento vs metas contractuales =================', '// ================= ÚLTIMOS HECHOS =================')
hechos_js = script_full[script_full.index('// ================= ÚLTIMOS HECHOS ================='):]

new_script = (
    helpers + nav_js +
    health_js + resumen_js + gestion_js + empresas_js + ventas_js +
    historia_js + resumen_cumpl_js + hechos_js
)

# ---------- 5. Assemble ----------
new_html = head + body_new + "<script>\nconst DATA = " + new_data_json + ";\n" + new_script + "</script>\n\n</body>\n</html>\n"

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(new_html)

print("Wrote", OUT, "size:", len(new_html))

# ---------- 6. Mobile CSS (baked in, no manual step needed) ----------
mobile_css = """  .table-scroll{overflow-x:auto}
  @media(max-width:768px){
    body{font-size:13px}
    .container{padding:8px}
    .card{padding:10px}
    table{font-size:11.5px}
    th,td{padding:5px 6px}
    .hca-firma-box{padding:14px 4px 6px}
  }
  @media(max-width:420px){
    body{font-size:12px}
    table{font-size:10.5px}
    th,td{padding:4px 4px}
  }
"""
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()
if "</style>" in final_html:
    final_html = final_html.replace("</style>", mobile_css + "</style>", 1)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(final_html)
    print("mobile CSS aplicado")
else:
    print("AVISO: no se encontro el anchor de CSS, revisar manualmente")

# ---------- 7. Resumen a nivel de EQUIPO (26-ago-2026, a pedido de Luis) ----------
# Luis pidio ir "hoja por hoja". Primera hoja: Resumen.
#   - Resumen ya NO muestra nada por-asesor (eso vive en Gestion/Empresas/Ventas).
#   - Los 2 graficos de arriba (tendencia de ventas, empresas por estado) se
#     mantienen igual.
#   - Las 2 tablas por-asesor que estaban abajo salen de Resumen: la de Ventas
#     se reubica en la seccion Ventas (renombrada "Ejecucion vs. meta"), la de
#     Gestion se reubica en Gestion > Equipo, pero sin el % (Luis dijo que ahi
#     "no ve la gestion como tal") -> se deja solo Estado + Meses activo +
#     rango Desde/Hasta (usando active_months, que ya trae el pipeline).
#   - En su lugar, Resumen ahora habla de Ventas/Empresas/Gestion (incl. medios
#     de contacto) a nivel de EQUIPO.
#   - Se cambia la palabra "Cumplimiento" por "Ejecucion" en lo que se toco.
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

# --- 7a. HTML: Resumen -> quitar las 2 tablas por-asesor, agregar 3 bloques de equipo ---
old_resumen_tablas = '''      <div class="grid2">
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Cumplimiento vs. meta contractual — Ventas (por asesor)</span></div>
          <div class="table-scroll">
          <table><thead><tr><th>Asesor</th><th>Meses activo</th><th>Ejecutado</th><th>Meta a la fecha</th><th>% Cumpl.</th></tr></thead><tbody id="tblResumenVentasMeta"></tbody></table>
          </div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Cumplimiento vs. meta contractual — Gestiones (por asesor)</span></div>
          <div class="table-scroll">
          <table><thead><tr><th>Asesor</th><th>Meses activo</th><th>% Cumpl. gestión</th><th>Estado</th></tr></thead><tbody id="tblResumenGestionMeta"></tbody></table>
          </div>
        </div>
      </div>
    </section>'''
new_resumen_equipo = '''      <div class="grid2">
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Ejecución de Ventas (equipo)</span></div>
          <div class="kpi-grid" id="resumenVentasEquipo"></div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Ejecución de Empresas (equipo)</span></div>
          <div class="kpi-grid" id="resumenEmpresasEquipo"></div>
        </div>
      </div>
      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ejecución de Gestión (equipo) — por frente de contrato</span></div>
        <div class="kpi-grid" id="resumenGestionEquipo"></div>
      </div>
    </section>'''
assert old_resumen_tablas in final_html, "No se encontro el bloque de tablas de Resumen a reemplazar"
final_html = final_html.replace(old_resumen_tablas, new_resumen_equipo)

# --- 7b. HTML: Ventas -> agregar tabla "Ejecución vs. meta — Ventas (por asesor)" ---
old_ventas_anchor = '''      <div class="kpi-grid" id="ventasKpis"></div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Tendencia mensual (según filtro)</span></div>'''
new_ventas_anchor = '''      <div class="kpi-grid" id="ventasKpis"></div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ejecución vs. meta — Ventas (por asesor)</span></div>
        <div class="table-scroll">
        <table><thead><tr><th>Asesor</th><th>Meses activo</th><th>Ejecutado</th><th>Meta a la fecha</th><th>% Ejecución</th></tr></thead><tbody id="tblVentasEjecucionAsesor"></tbody></table>
        </div>
      </div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Tendencia mensual (según filtro)</span></div>'''
assert old_ventas_anchor in final_html, "No se encontro el anchor de Ventas"
final_html = final_html.replace(old_ventas_anchor, new_ventas_anchor)

# --- 7c. HTML: Gestion > Equipo -> agregar tabla "Actividad del equipo — meses activos" ---
old_gestion_anchor = '''          <div class="card">
            <div class="card-title"><span><span class="dot"></span>Medios de contacto utilizados (equipo, volumen)</span></div>
            <div class="chart-box sm"><canvas id="chGestionMedios"></canvas></div>
          </div>
        </div>
      </div>

      <div class="subpanel" id="gsub-asesor">'''
new_gestion_anchor = '''          <div class="card">
            <div class="card-title"><span><span class="dot"></span>Medios de contacto utilizados (equipo, volumen)</span></div>
            <div class="chart-box sm"><canvas id="chGestionMedios"></canvas></div>
          </div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Actividad del equipo — meses activos</span></div>
          <div class="table-scroll">
          <table><thead><tr><th>Asesor</th><th>Estado</th><th>Meses activo</th><th>Desde</th><th>Hasta</th></tr></thead><tbody id="tblGestionActividadAsesor"></tbody></table>
          </div>
        </div>
      </div>

      <div class="subpanel" id="gsub-asesor">'''
assert old_gestion_anchor in final_html, "No se encontro el anchor de Gestion > Equipo"
final_html = final_html.replace(old_gestion_anchor, new_gestion_anchor)

# --- 7d. JS: Resumen -> renombrar "Cumplimiento" a "Ejecución", fechas dinamicas (ya no fijas en mar-jul), + 3 bloques nuevos ---
old_resumen_kpis_js = '''document.getElementById('resumenKpis').innerHTML = `
  <div class="kpi"><div class="kv">${contractAvgPct.toFixed(0)}%</div><div class="kl">Cumplimiento contractual (Gestión)</div></div>
  <div class="kpi acc"><div class="kv">${fmtM(ventasD.total_ejecutado_5m)}</div><div class="kl">Ventas ejecutadas mar-jul</div></div>
  <div class="kpi"><div class="kv">${fmtM(ventasD.meta_ejecutado_5m)}</div><div class="kl">Meta proyectada mar-jul (${ventasD.cumpl_ejecutado_5m_pct}% cumplido)</div></div>
  <div class="kpi"><div class="kv">${DATA.empresas_agg.per_counts['Contactada - contrato actual']||0}</div><div class="kl">Empresas contactadas (contrato actual)</div></div>
  <div class="kpi bad"><div class="kv">${DATA.empresas_agg.per_counts['No contactada']||0}</div><div class="kl">Empresas no contactadas</div></div>
`;'''
new_resumen_kpis_js = '''const mesesTendencia = ventasD.tendencia.map(t=>t.mes);
const rangoTendencia = mesesTendencia.length? (mesesTendencia[0]+'-'+mesesTendencia[mesesTendencia.length-1]) : '';
const acumEjecutadoEq = ventasD.tendencia.reduce((s,t)=>s+t.ventas,0);
const acumMetaEq = ventasD.tendencia.reduce((s,t)=>s+t.meta,0);
const pctAcumEquipo = acumMetaEq>0 ? (acumEjecutadoEq/acumMetaEq*100) : 0;
document.getElementById('resumenKpis').innerHTML = `
  <div class="kpi"><div class="kv">${contractAvgPct.toFixed(0)}%</div><div class="kl">Ejecución contractual (Gestión)</div></div>
  <div class="kpi acc"><div class="kv">${fmtM(acumEjecutadoEq)}</div><div class="kl">Ventas ejecutadas ${rangoTendencia}</div></div>
  <div class="kpi"><div class="kv">${fmtM(acumMetaEq)}</div><div class="kl">Meta acumulada ${rangoTendencia} (${pctAcumEquipo.toFixed(0)}% ejecutado)</div></div>
  <div class="kpi"><div class="kv">${DATA.empresas_agg.per_counts['Contactada - contrato actual']||0}</div><div class="kl">Empresas contactadas (contrato actual)</div></div>
  <div class="kpi bad"><div class="kv">${DATA.empresas_agg.per_counts['No contactada']||0}</div><div class="kl">Empresas no contactadas</div></div>
`;

// ---- Ejecución a nivel de EQUIPO (reemplaza las 2 tablas por-asesor que salieron de Resumen) ----
const mesActualTendEq = ventasD.tendencia[ventasD.tendencia.length-1];
const pctMesEquipo = mesActualTendEq.meta>0 ? (mesActualTendEq.ventas/mesActualTendEq.meta*100) : 0;
document.getElementById('resumenVentasEquipo').innerHTML = `
  <div class="kpi"><div class="kv">${fmtM(mesActualTendEq.ventas)}</div><div class="kl">Ejecutado ${mesActualTendEq.mes}${mesActualTendEq.parcial?' (parcial)':''}</div></div>
  <div class="kpi"><div class="kv">${pctMesEquipo.toFixed(0)}%</div><div class="kl">% Ejecución del mes</div></div>
  <div class="kpi acc"><div class="kv">${fmtM(acumEjecutadoEq)}</div><div class="kl">Ejecutado acumulado (${rangoTendencia})</div></div>
  <div class="kpi"><div class="kv">${pctAcumEquipo.toFixed(0)}%</div><div class="kl">% Ejecución acumulada</div></div>
`;

const totalEmpEquipo = DATA.empresas_agg.total;
const contactadasEquipo = DATA.empresas_agg.per_counts['Contactada - contrato actual']||0;
const noContactadasEquipo = DATA.empresas_agg.per_counts['No contactada']||0;
document.getElementById('resumenEmpresasEquipo').innerHTML = `
  <div class="kpi"><div class="kv">${fmtN(totalEmpEquipo)}</div><div class="kl">Empresas en el padrón</div></div>
  <div class="kpi acc"><div class="kv">${totalEmpEquipo?((contactadasEquipo/totalEmpEquipo)*100).toFixed(0):0}%</div><div class="kl">% Contactadas (contrato actual)</div></div>
  <div class="kpi bad"><div class="kv">${fmtN(noContactadasEquipo)}</div><div class="kl">Sin contactar</div></div>
`;

document.getElementById('resumenGestionEquipo').innerHTML = contract.categories.map(cat=>{
  const inds = cat.indicators.filter(i=>!i.pending);
  let real=0, expected=0;
  inds.forEach(i=>{ real += i.real; expected += i.meta_6m*contract.elapsed_fraction; });
  const pct = expected>0 ? Math.min(real/expected,1.5)*100 : 0;
  return `<div class="kpi"><div class="kv">${pct.toFixed(0)}%</div><div class="kl">${cat.name} — % ejecución</div></div>`;
}).join('');'''
assert old_resumen_kpis_js in final_html, "No se encontro el JS de resumenKpis"
final_html = final_html.replace(old_resumen_kpis_js, new_resumen_kpis_js)

# --- 7e. JS: reemplazar el IIFE que llenaba las 2 tablas por-asesor de Resumen ----
# (ahora llenan las tablas reubicadas en Ventas y en Gestion > Equipo)
old_cumpl_iife = '''(function(){
  const rowsVen = advisorsFull.map(a=>{
    const r = ventasRankByName[a.name];
    if (!r || !r.meta_acumulada_5m) return null;
    const pct = r.meta_acumulada_5m>0 ? (r.total_acumulado/r.meta_acumulada_5m*100) : null;
    return {name:a.name, meses:a.meses_activos||r.meses_activos, real:r.total_acumulado, meta:r.meta_acumulada_5m, pct};
  }).filter(Boolean).sort((a,b)=>(b.pct||0)-(a.pct||0));
  document.getElementById('tblResumenVentasMeta').innerHTML = rowsVen.map(r=>{
    const cls = r.pct!=null? statusClass(r.pct):'na';
    return `<tr><td>${r.name}</td><td>${r.meses}</td><td>${fmt(r.real)}</td><td>${fmt(r.meta)}</td><td><span class="badge ${cls||'ok'}">${r.pct!=null?r.pct.toFixed(0)+'%':'—'}</span></td></tr>`;
  }).join('');

  const rowsGes = advisorsFull.slice().sort((a,b)=>b.accumulated.global_pct-a.accumulated.global_pct).map(a=>{
    const pct = a.accumulated.global_pct*100;
    return {name:a.name, meses:a.meses_activos, pct, active:a.active};
  });
  document.getElementById('tblResumenGestionMeta').innerHTML = rowsGes.map(r=>{
    const cls = statusClass(r.pct);
    return `<tr><td>${r.name}</td><td>${r.meses}</td><td><span class="badge ${cls||'ok'}">${r.pct.toFixed(0)}%</span></td><td><span class="badge ${r.active===false?'off':'on'}">${r.active===false?'Inactivo':'Activo'}</span></td></tr>`;
  }).join('');
})();'''
new_asesor_tables_iife = '''(function(){
  const rowsVen = advisorsFull.map(a=>{
    const r = ventasRankByName[a.name];
    if (!r || !r.meta_acumulada_5m) return null;
    const pct = r.meta_acumulada_5m>0 ? (r.total_acumulado/r.meta_acumulada_5m*100) : null;
    return {name:a.name, meses:a.meses_activos||r.meses_activos, real:r.total_acumulado, meta:r.meta_acumulada_5m, pct};
  }).filter(Boolean).sort((a,b)=>(b.pct||0)-(a.pct||0));
  const tblVenEj = document.getElementById('tblVentasEjecucionAsesor');
  if (tblVenEj) tblVenEj.innerHTML = rowsVen.map(r=>{
    const cls = r.pct!=null? statusClass(r.pct):'na';
    return `<tr><td>${r.name}</td><td>${r.meses}</td><td>${fmt(r.real)}</td><td>${fmt(r.meta)}</td><td><span class="badge ${cls||'ok'}">${r.pct!=null?r.pct.toFixed(0)+'%':'—'}</span></td></tr>`;
  }).join('');

  // Gestion > Equipo: solo Estado + Meses activo + rango Desde/Hasta (sin %, a pedido de Luis)
  const rowsGesAct = advisorsFull.slice().sort((a,b)=>a.name.localeCompare(b.name)).map(a=>{
    const meses = (a.active_months||[]).slice().sort();
    const gesLbl = DATA.gestiones.month_labels || {};
    const desde = meses.length? (gesLbl[meses[0]] || meses[0]) : '—';
    const hasta = meses.length? (gesLbl[meses[meses.length-1]] || meses[meses.length-1]) : '—';
    return {name:a.name, active:a.active, mesesN:a.meses_activos, desde, hasta};
  });
  const tblGesAct = document.getElementById('tblGestionActividadAsesor');
  if (tblGesAct) tblGesAct.innerHTML = rowsGesAct.map(r=>`
    <tr><td>${r.name}</td><td><span class="badge ${r.active===false?'off':'on'}">${r.active===false?'Inactivo':'Activo'}</span></td><td>${r.mesesN}</td><td>${r.desde}</td><td>${r.hasta}</td></tr>
  `).join('');
})();'''
assert old_cumpl_iife in final_html, "No se encontro el IIFE de las tablas por-asesor de Resumen"
final_html = final_html.replace(old_cumpl_iife, new_asesor_tables_iife)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 7 aplicado: Resumen a nivel de equipo (Ventas/Empresas/Gestion), tablas por-asesor reubicadas en Ventas y Gestion>Equipo.")

# ---------- 8. Hoja de Gestion (26-ago-2026, a pedido de Luis) ----------
# Resumen de lo pedido en esta ronda:
#  a) Quitar el indicador "Ventas efectivas ($)" (siempre "sin dato") de Gestion;
#     las ventas reales ya se ven en Ventas/Historia Comercial.
#  b) Empresas asignadas/gestionadas/faltantes se mueven de Gestion>Por Asesor a
#     Empresas (ahi se calculan segun el filtro de Asesor que ya existe).
#  c) Renombrar/():"Ejecutado marzo-julio" -> sin rango de meses fijo (se veia
#     "pegado" en el tiempo); "Ejecutado Mar-Jul" (tab ACC) -> "Acumulado (contrato)".
#  d) Quitar la pestaña "Contrato Cajamag" de Gestion.
#  e) Agregar "Medios de contacto real vs. meta" (equipo, acumulado del contrato)
#     a Gestion > Equipo (usa contract.categories, que ya trae Llamadas/WhatsApp/
#     Correos con meta_6m -- es la unica fuente con metas reales, por eso queda
#     "acumulado" y no cambia con el filtro de mes).
#  f) Filtro por mes en Gestion > Equipo (Acumulado + cada mes), recalculando
#     ranking/zonas/graficas de indicadores y el volumen de medios de contacto.
#     OJO: active_months todavia no incluye agosto para nadie (el pipeline de
#     gestiones no se ha vuelto a correr desde el refresh de hoy) -> si Luis
#     filtra "Agosto" va a ver el aviso de "aun no hay datos" hasta la proxima
#     corrida de gestiones.
#  g) "Posicion" del asesor seleccionado: puesto en el contrato (acumulado) y
#     puesto en el mes que este seleccionado en el selector de periodo que ya
#     existia en Por Asesor.
#  NOTA para Luis (no se implementa aqui): saber si una gestion "quedo en
#  negociacion" requiere cruzar cada gestion con los negocios (deals) de Bitrix
#  por empresa/contacto y fecha -- ese cruce no esta en los datos que tenemos
#  hoy (raw_gestiones no trae un ID de negocio asociado). Es una extraccion
#  nueva de Bitrix, no un ajuste de pantalla.
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

# --- 8a-HTML. Quitar pestaña "Contrato Cajamag" (nav + subpanel) ---
old_nav_gsub = '''        <div class="subtab active" data-gsub="equipo">Equipo</div>
        <div class="subtab" data-gsub="asesor">Por Asesor</div>
        <div class="subtab" data-gsub="contrato">Contrato Cajamag</div>
      </div>'''
new_nav_gsub = '''        <div class="subtab active" data-gsub="equipo">Equipo</div>
        <div class="subtab" data-gsub="asesor">Por Asesor</div>
      </div>'''
assert old_nav_gsub in final_html, "No se encontro el nav de subtabs de Gestion"
final_html = final_html.replace(old_nav_gsub, new_nav_gsub)

old_gsub_contrato = '''      <div class="subpanel" id="gsub-contrato">
        <div class="grid2">
          <div class="card">
            <div class="card-title"><span><span class="dot"></span>Promoción — % cumplimiento</span></div>
            <div class="chart-box sm"><canvas id="chContratoPromocion"></canvas></div>
          </div>
          <div class="card">
            <div class="card-title"><span><span class="dot"></span>Mantenimiento — % cumplimiento</span></div>
            <div class="chart-box sm"><canvas id="chContratoMantenimiento"></canvas></div>
          </div>
        </div>
        <div class="grid2">
          <div class="card">
            <div class="card-title"><span><span class="dot"></span>Venta — % cumplimiento</span></div>
            <div class="chart-box sm"><canvas id="chContratoVenta"></canvas></div>
          </div>
          <div class="card">
            <div class="card-title"><span><span class="dot"></span>Medios de contacto — % cumplimiento</span></div>
            <div class="chart-box sm"><canvas id="chContratoContacto"></canvas></div>
          </div>
        </div>
        <div class="table-scroll">
        <table><thead><tr><th>Indicador</th><th>Real</th><th>Meta esperada</th><th>Meta 6m</th><th>Estado</th></tr></thead><tbody id="tblContrato"></tbody></table>
        </div>
      </div>
    </section>'''
new_gsub_contrato = '''    </section>'''
assert old_gsub_contrato in final_html, "No se encontro el subpanel gsub-contrato"
final_html = final_html.replace(old_gsub_contrato, new_gsub_contrato)

# --- 8b-HTML. Equipo: agregar filtro por mes + tarjeta "medios con meta" ---
old_equipo_top = '''      <div class="subpanel active" id="gsub-equipo">
        <div class="kpi-grid" id="gestionKpis"></div>'''
new_equipo_top = '''      <div class="subpanel active" id="gsub-equipo">
        <div class="month-tabs" id="gestionEquipoMonthTabs"></div>
        <div class="kpi-grid" id="gestionKpis"></div>'''
assert old_equipo_top in final_html, "No se encontro el inicio de gsub-equipo"
final_html = final_html.replace(old_equipo_top, new_equipo_top)

old_medios_anchor = '''          <div class="card">
            <div class="card-title"><span><span class="dot"></span>Medios de contacto utilizados (equipo, volumen)</span></div>
            <div class="chart-box sm"><canvas id="chGestionMedios"></canvas></div>
          </div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Actividad del equipo — meses activos</span></div>'''
new_medios_anchor = '''          <div class="card">
            <div class="card-title"><span><span class="dot"></span>Medios de contacto utilizados (equipo, volumen)</span></div>
            <div class="chart-box sm"><canvas id="chGestionMedios"></canvas></div>
          </div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Medios de contacto — real vs. meta (equipo, acumulado del contrato)</span></div>
          <div class="kpi-grid" id="gestionMediosMetas"></div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Actividad del equipo — meses activos</span></div>'''
assert old_medios_anchor in final_html, "No se encontro el anchor de medios de contacto en Equipo"
final_html = final_html.replace(old_medios_anchor, new_medios_anchor)

# --- 8c-HTML. Por Asesor: gestionAsesorEmpresas -> gestionAsesorPosicion (se mueve empresas a Empresas, se agrega posicion) ---
old_asesor_empresas_div = '''        <div class="kpi-grid" id="gestionAsesorDetalle"></div>
        <div class="kpi-grid" id="gestionAsesorEmpresas" style="margin-top:10px;"></div>'''
new_asesor_empresas_div = '''        <div class="kpi-grid" id="gestionAsesorDetalle"></div>
        <div class="kpi-grid" id="gestionAsesorPosicion" style="margin-top:10px;"></div>'''
assert old_asesor_empresas_div in final_html, "No se encontro el div gestionAsesorEmpresas"
final_html = final_html.replace(old_asesor_empresas_div, new_asesor_empresas_div)

# --- 8d-HTML. Ventas: quitar el rango de meses fijo del section-desc ---
old_ventas_desc = '''      <div class="section-desc">Ejecutado marzo-julio — segmenta por mes, asesor, zona, tipo de venta y servicio: tarjetas y gráficas se recalculan con el filtro.</div>'''
new_ventas_desc = '''      <div class="section-desc">Ejecutado — segmenta por mes, asesor, zona, tipo de venta y servicio: tarjetas y gráficas se recalculan con el filtro.</div>'''
assert old_ventas_desc in final_html, "No se encontro el section-desc de Ventas"
final_html = final_html.replace(old_ventas_desc, new_ventas_desc)

# --- 8e-JS. Resumen: quitar el rango de meses de las etiquetas "Ejecutado ..." ---
old_resumen_rango1 = "<div class=\"kl\">Ventas ejecutadas ${rangoTendencia}</div>"
new_resumen_rango1 = "<div class=\"kl\">Ventas ejecutadas</div>"
assert old_resumen_rango1 in final_html
final_html = final_html.replace(old_resumen_rango1, new_resumen_rango1)

old_resumen_rango2 = "<div class=\"kl\">Meta acumulada ${rangoTendencia} (${pctAcumEquipo.toFixed(0)}% ejecutado)</div>"
new_resumen_rango2 = "<div class=\"kl\">Meta acumulada (${pctAcumEquipo.toFixed(0)}% ejecutado)</div>"
assert old_resumen_rango2 in final_html
final_html = final_html.replace(old_resumen_rango2, new_resumen_rango2)

old_resumen_rango3 = "<div class=\"kl\">Ejecutado acumulado (${rangoTendencia})</div>"
new_resumen_rango3 = "<div class=\"kl\">Ejecutado acumulado</div>"
assert old_resumen_rango3 in final_html
final_html = final_html.replace(old_resumen_rango3, new_resumen_rango3)

# --- 8f-JS. Por Asesor: tab "ACC" sin rango de meses fijo ---
old_acc_tab = '''<div class="month-tab accent ${gestionCurrentPeriod==='ACC'?'active':''}" data-period="ACC">Ejecutado Mar–Jul</div>'''
new_acc_tab = '''<div class="month-tab accent ${gestionCurrentPeriod==='ACC'?'active':''}" data-period="ACC">Acumulado (contrato)</div>'''
assert old_acc_tab in final_html
final_html = final_html.replace(old_acc_tab, new_acc_tab)

# --- 8g-JS. Bloque grande de Equipo: pasa a ser funcion parametrizada por periodo (Acumulado o un mes) ---
old_equipo_block = '''const teamAvgPct = activeAdvisors.reduce((s,a)=>s+a.accumulated.global_pct,0)/activeAdvisors.length*100;
document.getElementById('gestionKpis').innerHTML = `
  <div class="kpi"><div class="kv">${activeAdvisors.length}</div><div class="kl">Asesores activos</div><div class="ks">de ${advisorsFull.length} en el equipo</div></div>
  <div class="kpi acc"><div class="kv">${teamAvgPct.toFixed(0)}%</div><div class="kl">Cumplimiento promedio del equipo</div></div>
  <div class="kpi"><div class="kv">${contractAvgPct.toFixed(0)}%</div><div class="kl">Cumplimiento contractual</div></div>
`;
const gestionRank = advisorsFull.slice().sort((a,b)=>b.accumulated.global_pct-a.accumulated.global_pct);
document.getElementById('gestionLeaderboard').innerHTML = gestionRank.map((a,i)=>{
  const pct = a.accumulated.global_pct*100, cls = statusClass(pct);
  const nMeses = a.meses_activos||0;
  return `<div class="lb-row"><div class="lb-rank ${i===0?'top1':''}">${i+1}</div>
    <div class="lb-name" title="${a.name}">${a.name}
      <span class="badge ${a.active===false?'off':'on'}" style="margin-left:6px;">${a.active===false?'Inactivo':'Activo'}</span>
      <span class="badge" style="background:#eef0ee;color:var(--text-muted);margin-left:4px;">${nMeses} ${nMeses===1?'mes':'meses'}</span>
    </div>
    <div class="lb-bar-track"><div class="lb-bar-fill ${cls}" style="width:${Math.min(pct,100)}%"></div></div>
    <div class="lb-val">${pct.toFixed(0)}%</div></div>`;
}).join('');

// ---- Por zona: atribución mes a mes (usa el perfil real de cada mes, no el perfil actual estático) ----
const zonaGestion = {};
const zonaAdvisorSet = {};
advisorsFull.forEach(a=>{
  const activeMonths = a.active_months || DATA.gestiones.months;
  activeMonths.forEach(ym=>{
    const md = a.months[ym];
    if(!md) return;
    const z = md.perfil || a.current_profile || 'Sin zona';
    if(!zonaGestion[z]) zonaGestion[z] = {};
    Object.entries(md.indicators).forEach(([k,d])=>{
      if(d.na) return;
      if(!zonaGestion[z][k]) zonaGestion[z][k] = {real:0, meta:0};
      zonaGestion[z][k].real += (d.real||0); zonaGestion[z][k].meta += (d.meta||0);
    });
  });
  const z2 = a.current_profile||'Sin zona';
  if(!zonaAdvisorSet[z2]) zonaAdvisorSet[z2] = new Set();
  zonaAdvisorSet[z2].add(a.name);
});
document.getElementById('gestionZonaCards').innerHTML = Object.entries(zonaGestion).map(([z,inds])=>{
  const pcts = Object.values(inds).filter(v=>v.meta>0).map(v=>Math.min(v.real/v.meta,1.5));
  const pctAvg = pcts.length? (pcts.reduce((s,p)=>s+p,0)/pcts.length*100) : 0;
  const nAse = zonaAdvisorSet[z] ? zonaAdvisorSet[z].size : 0;
  return `<div class="zona-card"><h3>${z}</h3><div class="zona-row">Asesores <b>${nAse}</b></div><div class="zona-row">Cumplimiento promedio <b>${pctAvg.toFixed(0)}%</b></div></div>`;
}).join('');

// --- Actividad más realizada + grupos Promoción/Mantenimiento/Ventas ---
const IND_GROUPS = {
  'Promoción': ['Feria de servicios','Presentación de portafolio'],
  'Mantenimiento': ['Actividades de mantenimiento','Asesorías generales','Actualización de base de datos','Visita por primera vez'],
  'Ventas': ['Cotizaciones','Órdenes de compra','Órdenes de matrícula','Ventas efectivas ($)'],
};
const indTotals = {}; // {indicador: {real, meta, pctSum, pctN}}
activeAdvisors.forEach(a=>{
  Object.entries(a.accumulated.indicators).forEach(([k,d])=>{
    if(!indTotals[k]) indTotals[k] = {real:0, meta:0, pctSum:0, pctN:0};
    if (!d.na){ indTotals[k].real += d.real; indTotals[k].meta += d.meta; indTotals[k].pctSum += d.pct; indTotals[k].pctN++; }
  });
});
const indRanked = Object.entries(indTotals).sort((a,b)=>b[1].real-a[1].real);
new Chart(document.getElementById('chGestionActividad'),{
  type:'bar', data:{ labels: indRanked.map(([k])=>k),
    datasets:[{label:'Total ejecutado (equipo)', data: indRanked.map(([,v])=>v.real), backgroundColor:'#00685Eaa'}] },
  options:{indexAxis:'y', responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}}
});

// Ventas: cumplimiento real de monto vendido del equipo (activos), prorateado por meses activos
const ventasRankByName = {};
(ventasD.ranking||[]).forEach(r=>{ ventasRankByName[r.asesor]=r; });
let ventasRealSum=0, ventasMetaSum=0;
activeAdvisors.forEach(a=>{
  const r = ventasRankByName[a.name];
  if (r && r.meta_acumulada_5m){ ventasRealSum += r.total_acumulado; ventasMetaSum += r.meta_acumulada_5m; }
});
const ventasPctEquipo = ventasMetaSum>0 ? Math.min(ventasRealSum/ventasMetaSum,1.5)*100 : 0;

const grupoPct = Object.entries(IND_GROUPS).map(([g, inds])=>{
  let sum=0, n=0;
  inds.forEach(k=>{ const t = indTotals[k]; if (t && t.pctN){ sum += t.pctSum; n += t.pctN; } });
  if (g==='Ventas'){
    // combina cotizaciones/órdenes de compra con el cumplimiento real de monto vendido
    if (ventasMetaSum>0){ sum += ventasPctEquipo/100; n += 1; }
  }
  return [g, n? (sum/n*100) : 0];
});
new Chart(document.getElementById('chGestionGrupos'),{
  type:'bar', data:{ labels: grupoPct.map(x=>x[0]),
    datasets:[{label:'% cumplimiento promedio', data: grupoPct.map(x=>x[1].toFixed(1)), backgroundColor:['#1F2A44aa','#00685Eaa','#FF6900aa']}] },
  options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{y:{ticks:{callback:v=>v+'%'}}}}
});
document.getElementById('chGestionGrupos').closest('.card').insertAdjacentHTML('beforeend', `<div class="section-desc" style="margin-top:8px;">Nota: "Plan de bienestar" queda pendiente de incluir en Ventas — falta definir su fuente de datos.</div>`);

// ---- Medios de contacto utilizados (volumen, desde bitácora de gestiones) ----
const rawGes = DATA.gestiones.raw_gestiones || [];
const medioCounts = {};
rawGes.forEach(r=>{ const m = r.medio || 'Sin dato'; medioCounts[m] = (medioCounts[m]||0)+1; });
const medioSorted = Object.entries(medioCounts).sort((a,b)=>b[1]-a[1]);
new Chart(document.getElementById('chGestionMedios'),{
  type:'bar', data:{ labels: medioSorted.map(x=>x[0]), datasets:[{label:'Gestiones', data: medioSorted.map(x=>x[1]), backgroundColor:'#2E75B6aa'}] },
  options:{indexAxis:'y', responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}}
});

// KPIs adicionales: mejor indicador, actividad top, cotizaciones/OC a nivel equipo
const bestInd = Object.entries(indTotals).filter(([,v])=>v.pctN>0).sort((a,b)=>(b[1].pctSum/b[1].pctN)-(a[1].pctSum/a[1].pctN))[0];
const cotizTotal = indTotals['Cotizaciones'] || {real:0,meta:0};
const ocTotal = indTotals['Órdenes de compra'] || {real:0,meta:0};
document.getElementById('gestionKpis').insertAdjacentHTML('beforeend', `
  <div class="kpi ok"><div class="kv">${bestInd? (bestInd[1].pctSum/bestInd[1].pctN*100).toFixed(0)+'%':'—'}</div><div class="kl">Mejor indicador: ${bestInd?bestInd[0]:'—'}</div></div>
  <div class="kpi"><div class="kv">${indRanked.length?indRanked[0][0]:'—'}</div><div class="kl">Actividad más realizada (${indRanked.length?fmtN(indRanked[0][1].real):0})</div></div>
  <div class="kpi"><div class="kv">${fmtN(cotizTotal.real)}/${fmtN(cotizTotal.meta)}</div><div class="kl">Cotizaciones (equipo)</div></div>
  <div class="kpi"><div class="kv">${fmtN(ocTotal.real)}/${fmtN(ocTotal.meta)}</div><div class="kl">Órdenes de compra (equipo)</div></div>
`);'''
new_equipo_block = '''// --- Actividad más realizada + grupos Promoción/Mantenimiento/Ventas ---
// "Ventas efectivas ($)" se quita: siempre queda "sin dato" y ya se ve la venta real en Ventas/Historia.
const IND_GROUPS = {
  'Promoción': ['Feria de servicios','Presentación de portafolio'],
  'Mantenimiento': ['Actividades de mantenimiento','Asesorías generales','Actualización de base de datos','Visita por primera vez'],
  'Ventas': ['Cotizaciones','Órdenes de compra','Órdenes de matrícula'],
};
// Ventas: cumplimiento real de monto vendido del equipo (solo tiene sentido acumulado; no hay meta de venta por mes)
const ventasRankByName = {};
(ventasD.ranking||[]).forEach(r=>{ ventasRankByName[r.asesor]=r; });

let chGestionActividad, chGestionGrupos, chGestionMedios;
let gestionEquipoPeriod = 'ACC';

function renderGestionEquipo(period){
  gestionEquipoPeriod = period;
  const periodLabel = period==='ACC' ? 'Acumulado (contrato)' : (DATA.gestiones.month_labels[period]||period);
  const eligibles = period==='ACC' ? activeAdvisors : advisorsFull.filter(a=>(a.active_months||[]).includes(period));
  const getPd = (a)=> period==='ACC' ? a.accumulated : a.months[period];

  if (!eligibles.length){
    document.getElementById('gestionKpis').innerHTML = `<div class="section-desc" style="padding:10px 0;">Aún no hay gestiones marcadas como activas para <b>${periodLabel}</b> en la última actualización — prueba con otro mes o con "Acumulado (contrato)".</div>`;
    document.getElementById('gestionLeaderboard').innerHTML = '';
    document.getElementById('gestionZonaCards').innerHTML = '';
    if (chGestionActividad){ chGestionActividad.data.labels=[]; chGestionActividad.data.datasets[0].data=[]; chGestionActividad.update(); }
    if (chGestionGrupos){ chGestionGrupos.data.labels=[]; chGestionGrupos.data.datasets[0].data=[]; chGestionGrupos.update(); }
    if (chGestionMedios){ chGestionMedios.data.labels=[]; chGestionMedios.data.datasets[0].data=[]; chGestionMedios.update(); }
    return;
  }

  const teamAvgPct = eligibles.reduce((s,a)=>s+(getPd(a)?.global_pct||0),0)/eligibles.length*100;
  document.getElementById('gestionKpis').innerHTML = `
    <div class="kpi"><div class="kv">${eligibles.length}</div><div class="kl">Asesores ${period==='ACC'?'activos':'con datos — '+periodLabel}</div><div class="ks">de ${advisorsFull.length} en el equipo</div></div>
    <div class="kpi acc"><div class="kv">${teamAvgPct.toFixed(0)}%</div><div class="kl">Cumplimiento promedio del equipo</div></div>
    <div class="kpi"><div class="kv">${contractAvgPct.toFixed(0)}%</div><div class="kl">Cumplimiento contractual (acumulado, no cambia con el filtro)</div></div>
  `;

  const gestionRank = eligibles.slice().sort((a,b)=>(getPd(b)?.global_pct||0)-(getPd(a)?.global_pct||0));
  document.getElementById('gestionLeaderboard').innerHTML = gestionRank.map((a,i)=>{
    const pct = (getPd(a)?.global_pct||0)*100, cls = statusClass(pct);
    const nMeses = a.meses_activos||0;
    return `<div class="lb-row"><div class="lb-rank ${i===0?'top1':''}">${i+1}</div>
      <div class="lb-name" title="${a.name}">${a.name}
        <span class="badge ${a.active===false?'off':'on'}" style="margin-left:6px;">${a.active===false?'Inactivo':'Activo'}</span>
        <span class="badge" style="background:#eef0ee;color:var(--text-muted);margin-left:4px;">${nMeses} ${nMeses===1?'mes':'meses'}</span>
      </div>
      <div class="lb-bar-track"><div class="lb-bar-fill ${cls}" style="width:${Math.min(pct,100)}%"></div></div>
      <div class="lb-val">${pct.toFixed(0)}%</div></div>`;
  }).join('');

  // ---- Por zona ----
  const zonaGestion = {};
  const zonaAdvisorSet = {};
  eligibles.forEach(a=>{
    const pd = getPd(a);
    if (!pd) return;
    const z = pd.perfil || a.current_profile || 'Sin zona';
    if(!zonaGestion[z]) zonaGestion[z] = {};
    Object.entries(pd.indicators).forEach(([k,d])=>{
      if(d.na) return;
      if(!zonaGestion[z][k]) zonaGestion[z][k] = {real:0, meta:0};
      zonaGestion[z][k].real += (d.real||0); zonaGestion[z][k].meta += (d.meta||0);
    });
    if(!zonaAdvisorSet[z]) zonaAdvisorSet[z] = new Set();
    zonaAdvisorSet[z].add(a.name);
  });
  document.getElementById('gestionZonaCards').innerHTML = Object.entries(zonaGestion).map(([z,inds])=>{
    const pcts = Object.values(inds).filter(v=>v.meta>0).map(v=>Math.min(v.real/v.meta,1.5));
    const pctAvg = pcts.length? (pcts.reduce((s,p)=>s+p,0)/pcts.length*100) : 0;
    const nAse = zonaAdvisorSet[z] ? zonaAdvisorSet[z].size : 0;
    return `<div class="zona-card"><h3>${z}</h3><div class="zona-row">Asesores <b>${nAse}</b></div><div class="zona-row">Cumplimiento promedio <b>${pctAvg.toFixed(0)}%</b></div></div>`;
  }).join('');

  // ---- Actividad más realizada + grupos ----
  const indTotals = {};
  eligibles.forEach(a=>{
    const pd = getPd(a);
    if (!pd) return;
    Object.entries(pd.indicators).forEach(([k,d])=>{
      if(!indTotals[k]) indTotals[k] = {real:0, meta:0, pctSum:0, pctN:0};
      if (!d.na){ indTotals[k].real += d.real; indTotals[k].meta += d.meta; indTotals[k].pctSum += d.pct; indTotals[k].pctN++; }
    });
  });
  const indRanked = Object.entries(indTotals).sort((a,b)=>b[1].real-a[1].real);
  if (!chGestionActividad){
    chGestionActividad = new Chart(document.getElementById('chGestionActividad'),{
      type:'bar', data:{ labels: indRanked.map(([k])=>k),
        datasets:[{label:'Total ejecutado (equipo)', data: indRanked.map(([,v])=>v.real), backgroundColor:'#00685Eaa'}] },
      options:{indexAxis:'y', responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}}
    });
  } else {
    chGestionActividad.data.labels = indRanked.map(([k])=>k);
    chGestionActividad.data.datasets[0].data = indRanked.map(([,v])=>v.real);
    chGestionActividad.update();
  }

  let ventasRealSum=0, ventasMetaSum=0;
  if (period==='ACC'){
    eligibles.forEach(a=>{
      const r = ventasRankByName[a.name];
      if (r && r.meta_acumulada_5m){ ventasRealSum += r.total_acumulado; ventasMetaSum += r.meta_acumulada_5m; }
    });
  }
  const ventasPctEquipo = ventasMetaSum>0 ? Math.min(ventasRealSum/ventasMetaSum,1.5)*100 : 0;
  const grupoPct = Object.entries(IND_GROUPS).map(([g, inds])=>{
    let sum=0, n=0;
    inds.forEach(k=>{ const t = indTotals[k]; if (t && t.pctN){ sum += t.pctSum; n += t.pctN; } });
    if (g==='Ventas' && ventasMetaSum>0){ sum += ventasPctEquipo/100; n += 1; }
    return [g, n? (sum/n*100) : 0];
  });
  if (!chGestionGrupos){
    chGestionGrupos = new Chart(document.getElementById('chGestionGrupos'),{
      type:'bar', data:{ labels: grupoPct.map(x=>x[0]),
        datasets:[{label:'% cumplimiento promedio', data: grupoPct.map(x=>x[1].toFixed(1)), backgroundColor:['#1F2A44aa','#00685Eaa','#FF6900aa']}] },
      options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{y:{ticks:{callback:v=>v+'%'}}}}
    });
    document.getElementById('chGestionGrupos').closest('.card').insertAdjacentHTML('beforeend', `<div class="section-desc" style="margin-top:8px;">Nota: "Plan de bienestar" queda pendiente de incluir en Ventas — falta definir su fuente de datos. El componente "Ventas" solo suma el cumplimiento real de venta cuando se ve "Acumulado (contrato)".</div>`);
  } else {
    chGestionGrupos.data.labels = grupoPct.map(x=>x[0]);
    chGestionGrupos.data.datasets[0].data = grupoPct.map(x=>x[1].toFixed(1));
    chGestionGrupos.update();
  }

  // ---- Medios de contacto (volumen, desde bitácora), filtrado por el mismo periodo ----
  const rawGes = DATA.gestiones.raw_gestiones || [];
  const rawGesPeriodo = period==='ACC' ? rawGes : rawGes.filter(r=>(r.fecha||'').slice(0,7)===period);
  const medioCounts = {};
  rawGesPeriodo.forEach(r=>{ const m = r.medio || 'Sin dato'; medioCounts[m] = (medioCounts[m]||0)+1; });
  const medioSorted = Object.entries(medioCounts).sort((a,b)=>b[1]-a[1]);
  if (!chGestionMedios){
    chGestionMedios = new Chart(document.getElementById('chGestionMedios'),{
      type:'bar', data:{ labels: medioSorted.map(x=>x[0]), datasets:[{label:'Gestiones', data: medioSorted.map(x=>x[1]), backgroundColor:'#2E75B6aa'}] },
      options:{indexAxis:'y', responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}}
    });
  } else {
    chGestionMedios.data.labels = medioSorted.map(x=>x[0]);
    chGestionMedios.data.datasets[0].data = medioSorted.map(x=>x[1]);
    chGestionMedios.update();
  }

  // KPIs adicionales
  const bestInd = Object.entries(indTotals).filter(([,v])=>v.pctN>0).sort((a,b)=>(b[1].pctSum/b[1].pctN)-(a[1].pctSum/a[1].pctN))[0];
  const cotizTotal = indTotals['Cotizaciones'] || {real:0,meta:0};
  const ocTotal = indTotals['Órdenes de compra'] || {real:0,meta:0};
  document.getElementById('gestionKpis').insertAdjacentHTML('beforeend', `
    <div class="kpi ok"><div class="kv">${bestInd? (bestInd[1].pctSum/bestInd[1].pctN*100).toFixed(0)+'%':'—'}</div><div class="kl">Mejor indicador: ${bestInd?bestInd[0]:'—'}</div></div>
    <div class="kpi"><div class="kv">${indRanked.length?indRanked[0][0]:'—'}</div><div class="kl">Actividad más realizada (${indRanked.length?fmtN(indRanked[0][1].real):0})</div></div>
    <div class="kpi"><div class="kv">${fmtN(cotizTotal.real)}/${fmtN(cotizTotal.meta)}</div><div class="kl">Cotizaciones (equipo)</div></div>
    <div class="kpi"><div class="kv">${fmtN(ocTotal.real)}/${fmtN(ocTotal.meta)}</div><div class="kl">Órdenes de compra (equipo)</div></div>
  `);
}

// ---- Medios de contacto real vs. meta (equipo, acumulado del contrato) ----
// Unica fuente con metas reales por medio (Llamadas/WhatsApp/Correos) es el
// contrato de 6 meses -> por eso esta tarjeta no cambia con el filtro de mes.
document.getElementById('gestionMediosMetas').innerHTML = (contract.categories.find(c=>c.name==='Medios de contacto')?.indicators||[])
  .filter(i=>!i.pending).map(i=>{
    const expected = i.meta_6m*contract.elapsed_fraction;
    const pct = expected>0 ? Math.min(i.real/expected,1.5)*100 : 0;
    const cls = statusClass(pct);
    return `<div class="kpi ${cls}"><div class="kv">${pct.toFixed(0)}%</div><div class="kl">${i.name}</div><div class="ks">${fmtN(i.real)} / ${fmtN(i.meta_6m)} meta contrato</div></div>`;
  }).join('');

function buildGestionEquipoMonthTabs(){
  const tabs = document.getElementById('gestionEquipoMonthTabs');
  let h = `<div class="month-tab accent ${gestionEquipoPeriod==='ACC'?'active':''}" data-period="ACC">Acumulado (contrato)</div>`;
  DATA.gestiones.months.forEach(ym=>{
    h += `<div class="month-tab ${gestionEquipoPeriod===ym?'active':''}" data-period="${ym}">${DATA.gestiones.month_labels[ym]}</div>`;
  });
  tabs.innerHTML = h;
  tabs.querySelectorAll('.month-tab').forEach(t=>t.addEventListener('click',()=>{
    tabs.querySelectorAll('.month-tab').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    renderGestionEquipo(t.dataset.period);
  }));
}
buildGestionEquipoMonthTabs();
renderGestionEquipo('ACC');'''
assert old_equipo_block in final_html, "No se encontro el bloque de Equipo (leaderboard/zona/actividad/grupos/medios) a reemplazar"
final_html = final_html.replace(old_equipo_block, new_equipo_block)

# --- 8h-JS. Por Asesor: quitar "Ventas efectivas ($)" del detalle + mover empresas a Empresas + agregar Posición ---
old_render_asesor = '''function renderAsesorDetalle(){
  const a = advisorsFull.find(x=>x.name===selAsesorG.value) || activeAdvisors[0];
  const periodData = gestionCurrentPeriod==='ACC' ? a.accumulated : a.months[gestionCurrentPeriod];
  if (!periodData){ document.getElementById('gestionAsesorDetalle').innerHTML = '<div class="section-desc">Sin datos para este periodo.</div>'; return; }
  document.getElementById('gestionAsesorDetalle').innerHTML = Object.entries(periodData.indicators).map(([k,d])=>{
    if (d.na) return `<div class="kpi na"><div class="kv" style="color:#9AA1B0;">${d.reason==='sin_dato'?'Sin datos':(d.reason==='periodo_no_activo'?'Aún no ingresaba':'No aplica')}</div><div class="kl">${k}</div></div>`;
    const cls = statusClass(d.pct*100);
    return `<div class="kpi ${cls}"><div class="kv">${(d.pct*100).toFixed(0)}%</div><div class="kl">${k}</div><div class="ks">${d.real} / ${d.meta} meta</div></div>`;
  }).join('');

  document.getElementById('gestionAsesorEmpresas').innerHTML = `
    <div class="kpi"><div class="kv">${fmtN(a.empresas_asignadas||0)}</div><div class="kl">Empresas asignadas (este contrato)</div></div>
    <div class="kpi acc"><div class="kv">${fmtN(a.empresas_gestionadas_contrato||0)}</div><div class="kl">Empresas gestionadas</div></div>
    <div class="kpi bad"><div class="kv">${fmtN(a.empresas_faltantes_contrato||0)}</div><div class="kl">Empresas faltantes por gestionar</div></div>
  `;
  renderGestionesDetalle();
}'''
new_render_asesor = '''function computeGestionRank(period, advisorName){
  const eligibles = period==='ACC'
    ? advisorsFull.filter(x=>x.accumulated)
    : advisorsFull.filter(x=>(x.active_months||[]).includes(period));
  if (!eligibles.length) return null;
  const ranked = eligibles.slice().sort((x,y)=>{
    const px = period==='ACC'? x.accumulated.global_pct : x.months[period].global_pct;
    const py = period==='ACC'? y.accumulated.global_pct : y.months[period].global_pct;
    return py-px;
  });
  const idx = ranked.findIndex(x=>x.name===advisorName);
  return idx>=0 ? {pos:idx+1, total:ranked.length} : null;
}
function renderAsesorDetalle(){
  const a = advisorsFull.find(x=>x.name===selAsesorG.value) || activeAdvisors[0];
  const periodData = gestionCurrentPeriod==='ACC' ? a.accumulated : a.months[gestionCurrentPeriod];
  if (!periodData){ document.getElementById('gestionAsesorDetalle').innerHTML = '<div class="section-desc">Sin datos para este periodo.</div>'; return; }
  document.getElementById('gestionAsesorDetalle').innerHTML = Object.entries(periodData.indicators)
    .filter(([k])=>k!=='Ventas efectivas ($)')
    .map(([k,d])=>{
      if (d.na) return `<div class="kpi na"><div class="kv" style="color:#9AA1B0;">${d.reason==='sin_dato'?'Sin datos':(d.reason==='periodo_no_activo'?'Aún no ingresaba':'No aplica')}</div><div class="kl">${k}</div></div>`;
      const cls = statusClass(d.pct*100);
      return `<div class="kpi ${cls}"><div class="kv">${(d.pct*100).toFixed(0)}%</div><div class="kl">${k}</div><div class="ks">${d.real} / ${d.meta} meta</div></div>`;
    }).join('');

  // ---- Posición del asesor: en el contrato (acumulado) y en el mes seleccionado arriba ----
  const rankContrato = computeGestionRank('ACC', a.name);
  const rankMes = gestionCurrentPeriod!=='ACC' ? computeGestionRank(gestionCurrentPeriod, a.name) : null;
  const mesLbl = gestionCurrentPeriod!=='ACC' ? (DATA.gestiones.month_labels[gestionCurrentPeriod]||gestionCurrentPeriod) : '';
  document.getElementById('gestionAsesorPosicion').innerHTML = `
    <div class="kpi acc"><div class="kv">${rankContrato? '#'+rankContrato.pos+' de '+rankContrato.total : '—'}</div><div class="kl">Posición en gestiones del contrato (acumulado)</div></div>
    <div class="kpi ${gestionCurrentPeriod==='ACC'?'na':(rankMes?'ok':'na')}"><div class="kv">${gestionCurrentPeriod==='ACC' ? 'Elige un mes arriba' : (rankMes? '#'+rankMes.pos+' de '+rankMes.total : 'Aún sin datos de este mes')}</div><div class="kl">Posición en gestiones de ${mesLbl||'el mes seleccionado'}</div></div>
  `;
  renderGestionesDetalle();
}'''
assert old_render_asesor in final_html, "No se encontro renderAsesorDetalle"
final_html = final_html.replace(old_render_asesor, new_render_asesor)

# --- 8i-JS. Empresas: agregar asignadas/gestionadas/faltantes (segun el filtro de Asesor que ya existe) ---
old_empresas_kpis = '''  document.getElementById('empresasKpis').innerHTML = `
    <div class="kpi"><div class="kv">${fmtN(total)}</div><div class="kl">Empresas (según filtro)</div></div>
    <div class="kpi acc"><div class="kv">${fmtN(contActual)}</div><div class="kl">Contactadas contrato actual (${pct(contActual)}%)</div></div>
    <div class="kpi warn"><div class="kv">${fmtN(contAnterior)}</div><div class="kl">Solo contrato anterior (${pct(contAnterior)}%)</div></div>
    <div class="kpi bad"><div class="kv">${fmtN(noCont)}</div><div class="kl">No contactadas (${pct(noCont)}%)</div></div>
  `;'''
new_empresas_kpis = '''  document.getElementById('empresasKpis').innerHTML = `
    <div class="kpi"><div class="kv">${fmtN(total)}</div><div class="kl">Empresas (según filtro)</div></div>
    <div class="kpi acc"><div class="kv">${fmtN(contActual)}</div><div class="kl">Contactadas contrato actual (${pct(contActual)}%)</div></div>
    <div class="kpi warn"><div class="kv">${fmtN(contAnterior)}</div><div class="kl">Solo contrato anterior (${pct(contAnterior)}%)</div></div>
    <div class="kpi bad"><div class="kv">${fmtN(noCont)}</div><div class="kl">No contactadas (${pct(noCont)}%)</div></div>
  `;

  // ---- Asignadas/gestionadas/faltantes (26-ago-2026, a pedido de Luis: se movió aquí desde Gestión) ----
  // Sigue el mismo filtro de Asesor que ya existe arriba: si hay uno elegido, muestra sus 3 números;
  // si está en "Todos", suma el equipo activo completo.
  const aseSelEmp = document.getElementById('fEmpAse').value;
  let empAsigK, empGestK, empFaltK, empLblK;
  if (aseSelEmp){
    const aEmp = advisorsFull.find(x=>x.name===aseSelEmp);
    empAsigK = aEmp ? (aEmp.empresas_asignadas||0) : 0;
    empGestK = aEmp ? (aEmp.empresas_gestionadas_contrato||0) : 0;
    empFaltK = aEmp ? (aEmp.empresas_faltantes_contrato||0) : 0;
    empLblK = aseSelEmp;
  } else {
    empAsigK = activeAdvisors.reduce((s,x)=>s+(x.empresas_asignadas||0),0);
    empGestK = activeAdvisors.reduce((s,x)=>s+(x.empresas_gestionadas_contrato||0),0);
    empFaltK = activeAdvisors.reduce((s,x)=>s+(x.empresas_faltantes_contrato||0),0);
    empLblK = 'equipo';
  }
  document.getElementById('empresasKpis').insertAdjacentHTML('beforeend', `
    <div class="kpi"><div class="kv">${fmtN(empAsigK)}</div><div class="kl">Empresas asignadas — ${empLblK}</div></div>
    <div class="kpi acc"><div class="kv">${fmtN(empGestK)}</div><div class="kl">Empresas gestionadas (contrato)</div></div>
    <div class="kpi bad"><div class="kv">${fmtN(empFaltK)}</div><div class="kl">Faltantes por gestionar</div></div>
  `);'''
assert old_empresas_kpis in final_html, "No se encontro el bloque empresasKpis"
final_html = final_html.replace(old_empresas_kpis, new_empresas_kpis)

# --- 8j-JS. Quitar el JS de Contrato Cajamag (CRITICO: si no se quita, document.getElementById('tblContrato')
# devuelve null porque ya no existe ese elemento en el HTML, y esa linea revienta el resto del script
# (Empresas/Ventas/Historia/Ultimos Hechos dejarian de renderizar). ---
old_contrato_js = '''const CONTRATO_CHART_IDS = {'Promoción':'chContratoPromocion','Mantenimiento':'chContratoMantenimiento','Ventas':'chContratoVenta','Medios de contacto':'chContratoContacto'};
contract.categories.forEach(cat=>{
  const canvasId = CONTRATO_CHART_IDS[cat.name];
  if (!canvasId || !document.getElementById(canvasId)) return;
  const inds = cat.indicators.filter(i=>!i.pending);
  const pcts = inds.map(i=>{
    const expected = i.meta_6m*contract.elapsed_fraction;
    return expected>0 ? Math.min(i.real/expected,1.5)*100 : 0;
  });
  new Chart(document.getElementById(canvasId),{
    type:'bar', data:{ labels: inds.map(i=>i.name),
      datasets:[{label:'% cumplimiento', data: pcts.map(p=>p.toFixed(1)), backgroundColor:'#00685Eaa'}] },
    options:{indexAxis:'y', responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{ticks:{callback:v=>v+'%'}}}}
  });
});
document.getElementById('tblContrato').innerHTML = contractIndicatorsAll.map(i=>{
  if (i.pending) return `<tr><td>${i.name}</td><td colspan="3" style="color:var(--text-muted);">Pendiente</td><td><span class="badge na">Falta fuente</span></td></tr>`;
  const expected = i.meta_6m*contract.elapsed_fraction;
  const pct = expected>0? i.real/expected*100:0;
  const cls = statusClass(pct);
  return `<tr><td>${i.name}${i.partial?' *':''}</td><td>${fmtN(i.real)}</td><td>${fmtN(Math.round(expected))}</td><td>${fmtN(i.meta_6m)}</td><td><span class="badge ${cls||'ok'}">${pct.toFixed(0)}%</span></td></tr>`;
}).join('');'''
assert old_contrato_js in final_html, "No se encontro el JS de Contrato Cajamag a eliminar"
final_html = final_html.replace(old_contrato_js, "// (Contrato Cajamag eliminado de Operativo el 26-ago-2026, a pedido de Luis)")

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 8 aplicado: hoja de Gestion (equipo con filtro por mes + medios con meta + posicion por asesor), Contrato Cajamag eliminado (HTML+JS), empresas asignadas/gestionadas/faltantes movidas a Empresas, 'Ventas efectivas' quitada, rangos de meses fijos removidos de etiquetas.")

# ---------- 9. Hoja de Empresas (26-ago-2026, a pedido de Luis; REDISEÑADA 27-ago-2026) ----------
# a) tam "Sin dato" -> corregido en el dato mismo (backfill directo en el Master
#    + fix del ETL en etl_empresas.py); no requiere cambio de build aqui.
# b) "Cantidad de gestiones" por empresa (cruce raw_gestiones x NIT).
# c) 27-ago-2026, a pedido de Luis: "en vez de tener un listado de ilocalizables
#    y oportunidad de primer contacto, creame una variable ESTADO en detalle de
#    la empresa (en vez de la columna Ilocalizable) que diga si ya se encontro,
#    si en verdad esta ilocalizada, o si es primer contacto -- asi no tenemos
#    tres listas de excel". Se elimina la tarjeta "Oportunidad" y la tarjeta
#    "Ilocalizables" (y su hoja aparte del Excel) -- toda esa informacion ahora
#    vive como UN solo campo "Estado" en la tabla de Detalle de empresas (y en
#    su unico Excel), filtrable como cualquier otro campo. Tambien se elimina
#    el panel de filtro independiente que solo servia para el export (Luis:
#    "el filtro deberia quedar arriba de detalle de empresa") -- ahora hay un
#    UNICO panel de filtros (el que ya estaba arriba de KPIs/graficas/tabla),
#    con un nuevo selector "Estado", que controla tabla, graficas Y el Excel.
# NOTA para Luis (no implementado aqui): Direccion y Persona de contacto NO
# existen en empresas_full hoy -- se necesitaria un pull nuevo de Bitrix REST
# (crm.company + join a crm.contact via CONTACT_ID) para las ~5.764 empresas.
# Telefono SI existia en el dato y ya se agrega al Excel.
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

# --- 9a-HTML: filtro nuevo "Estado" en el panel de arriba (arriba de Detalle de empresa) ---
old_emp_filters = '''      <div class="filters">
        <div class="filter-group"><label>Buscar</label><input type="text" id="fEmpBuscar" placeholder="Nombre o NIT..."></div>
        <div class="filter-group"><label>Estado de contacto</label><select id="fEmpPer"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Tamaño</label><select id="fEmpTam"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Estado afiliación</label><select id="fEmpEst"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Asesor</label><select id="fEmpAse"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Equipo/Zona</label><select id="fEmpEq"><option value="">Todas</option></select></div>
        <div class="filter-group"><label>Dificultad</label><select id="fEmpDif"><option value="">Todas</option></select></div>
        <button class="filter-clear" id="btnClearEmp">Limpiar</button>
      </div>'''
new_emp_filters = '''      <div class="filters">
        <div class="filter-group"><label>Buscar</label><input type="text" id="fEmpBuscar" placeholder="Nombre o NIT..."></div>
        <div class="filter-group"><label>Estado de contacto</label><select id="fEmpPer"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Estado</label><select id="fEmpEstado"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Tamaño</label><select id="fEmpTam"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Estado afiliación</label><select id="fEmpEst"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Asesor</label><select id="fEmpAse"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Equipo/Zona</label><select id="fEmpEq"><option value="">Todas</option></select></div>
        <div class="filter-group"><label>Dificultad</label><select id="fEmpDif"><option value="">Todas</option></select></div>
        <button class="filter-clear" id="btnClearEmp">Limpiar</button>
      </div>'''
assert old_emp_filters in final_html, "No se encontro el panel de filtros de Empresas"
final_html = final_html.replace(old_emp_filters, new_emp_filters)

# --- 9b-HTML: tabla Detalle -> columna "Estado" (reemplaza "Ilocalizable"), +Gestiones,
#     boton de export se queda EN esta misma tarjeta (unico filtro, unica lista) ---
old_detalle_card = '''      <div class="card">
        <div class="card-title">
          <span><span class="dot"></span>Detalle de empresas (según filtro)</span>
          <button class="filter-clear" id="btnExportEmp">⬇ Exportar a Excel</button>
        </div>
        <div class="summary-strip" id="empSummaryStrip"></div>
        <div class="table-scroll">
        <table><thead><tr><th>Empresa</th><th>NIT</th><th>Tamaño</th><th>Asesor</th><th>Equipo</th><th>Estado contacto</th><th>Dificultad</th><th>Ilocalizable</th><th>Última gestión</th></tr></thead><tbody id="tblEmpresas"></tbody></table>
        </div>
      </div>
    </section>'''
new_detalle_card = '''      <div class="card">
        <div class="card-title">
          <span><span class="dot"></span>Detalle de empresas (según filtro)</span>
          <button class="filter-clear" id="btnExportEmp">⬇ Exportar a Excel</button>
        </div>
        <div class="summary-strip" id="empSummaryStrip"></div>
        <div class="table-scroll">
        <table><thead><tr><th>Empresa</th><th>NIT</th><th>Tamaño</th><th>Asesor</th><th>Equipo</th><th>Estado contacto</th><th>Dificultad</th><th>Estado</th><th>Última gestión</th><th>Gestiones</th></tr></thead><tbody id="tblEmpresas"></tbody></table>
        </div>
      </div>
    </section>'''
assert old_detalle_card in final_html, "No se encontro la tarjeta Detalle de empresas"
final_html = final_html.replace(old_detalle_card, new_detalle_card)

# --- 9c-JS: gestionesPorNit (cruce raw_gestiones x NIT) + estadoUnificado(r) ---
old_emp_top = '''const emp = DATA.empresas_agg;
const empFull = DATA.empresas_full;
const TAM_ORDER = ['Grande','Mediana','Pequeña','Micro','Sin dato'];'''
new_emp_top = '''const emp = DATA.empresas_agg;
const empFull = DATA.empresas_full;
const TAM_ORDER = ['Grande','Mediana','Pequeña','Micro','Sin dato'];

// Cantidad de gestiones por empresa (cruce por NIT contra la bitácora completa)
const gestionesPorNit = {};
(DATA.gestiones.raw_gestiones||[]).forEach(r=>{
  if (!r.nit) return;
  gestionesPorNit[r.nit] = (gestionesPorNit[r.nit]||0) + 1;
});

// Estado unificado (27-ago-2026, a pedido de Luis): reemplaza la vieja columna
// "Ilocalizable" (sí/no) + las listas separadas de "Oportunidad" e
// "Ilocalizables" por UN solo campo con 3 valores posibles.
function estadoUnificado(r){
  if (r.iloc) return 'Ilocalizable';
  if (r.per === 'No contactada') return 'Primer contacto';
  return 'Ya se encontró';
}
const ESTADO_ORDER = ['Ya se encontró','Primer contacto','Ilocalizable'];'''
assert old_emp_top in final_html, "No se encontro el inicio del bloque JS de Empresas"
final_html = final_html.replace(old_emp_top, new_emp_top)

# --- 9d-JS: poblar el nuevo selector "Estado" ---
old_populate_dif = '''populateSelect('fEmpDif', [...new Set(empFull.map(r=>r.dif))].sort());'''
new_populate_dif = '''populateSelect('fEmpDif', [...new Set(empFull.map(r=>r.dif))].sort());
populateSelect('fEmpEstado', ESTADO_ORDER);'''
assert old_populate_dif in final_html, "No se encontro populateSelect fEmpDif"
final_html = final_html.replace(old_populate_dif, new_populate_dif)

# --- 9e-JS: getEmpresasFiltered ahora tambien filtra por "Estado" (unico filtro, ya no hay uno aparte para el Excel) ---
old_get_filtered = '''function getEmpresasFiltered(){
  const q = document.getElementById('fEmpBuscar').value.trim().toLowerCase();
  const per = document.getElementById('fEmpPer').value;
  const tam = document.getElementById('fEmpTam').value;
  const est = document.getElementById('fEmpEst').value;
  const ase = document.getElementById('fEmpAse').value;
  const eq = document.getElementById('fEmpEq').value;
  const dif = document.getElementById('fEmpDif').value;
  let rows = empFull;
  if (q) rows = rows.filter(r => (r.nom||'').toLowerCase().includes(q) || (r.nit||'').includes(q));
  if (per) rows = rows.filter(r=>r.per===per);
  if (tam) rows = rows.filter(r=>r.tam===tam);
  if (est) rows = rows.filter(r=>r.est===est);
  if (ase) rows = rows.filter(r=>r.ase===ase);
  if (eq) rows = rows.filter(r=>r.eq===eq);
  if (dif) rows = rows.filter(r=>r.dif===dif);
  return rows;
}'''
new_get_filtered = '''function getEmpresasFiltered(){
  const q = document.getElementById('fEmpBuscar').value.trim().toLowerCase();
  const per = document.getElementById('fEmpPer').value;
  const estado = document.getElementById('fEmpEstado').value;
  const tam = document.getElementById('fEmpTam').value;
  const est = document.getElementById('fEmpEst').value;
  const ase = document.getElementById('fEmpAse').value;
  const eq = document.getElementById('fEmpEq').value;
  const dif = document.getElementById('fEmpDif').value;
  let rows = empFull;
  if (q) rows = rows.filter(r => (r.nom||'').toLowerCase().includes(q) || (r.nit||'').includes(q));
  if (per) rows = rows.filter(r=>r.per===per);
  if (estado) rows = rows.filter(r=>estadoUnificado(r)===estado);
  if (tam) rows = rows.filter(r=>r.tam===tam);
  if (est) rows = rows.filter(r=>r.est===est);
  if (ase) rows = rows.filter(r=>r.ase===ase);
  if (eq) rows = rows.filter(r=>r.eq===eq);
  if (dif) rows = rows.filter(r=>r.dif===dif);
  return rows;
}'''
assert old_get_filtered in final_html, "No se encontro getEmpresasFiltered"
final_html = final_html.replace(old_get_filtered, new_get_filtered)

# --- 9f-JS: tabla Detalle -> columna "Estado" (badge) +Gestiones; se quita el render de Oportunidad ---
old_tbl_tail = '''  document.getElementById('empSummaryStrip').innerHTML = `
    <div class="sitem"><b>${fmtN(rows.length)}</b>Empresas filtradas</div>
    <div class="sitem"><b>${fmtN(iloc)}</b>Ilocalizables</div>
    <div class="sitem"><b>${fmtN(noCont)}</b>No contactadas</div>
  `;
  const shown = rows.slice(0,400);
  document.getElementById('tblEmpresas').innerHTML = shown.map(r=>`
    <tr><td>${r.nom||'—'}</td><td>${r.nit||'—'}</td><td>${r.tam||'—'}</td><td>${r.ase||'—'}</td><td>${r.eq||'—'}</td>
    <td><span class="badge ${r.per==='No contactada'?'bad':(r.per==='Contactada - contrato actual'?'ok':'warn')}">${r.per}</span></td>
    <td>${r.dif}</td><td>${r.iloc?'<span class="badge bad">Sí</span>':'—'}</td><td>${r.fue||'—'}</td></tr>
  `).join('') + (rows.length>400? `<tr><td colspan="9" style="text-align:center;color:var(--text-muted);font-style:italic;">Mostrando 400 de ${rows.length} — afina el filtro o exporta a Excel.</td></tr>`:'');
}'''
new_tbl_tail = '''  document.getElementById('empSummaryStrip').innerHTML = `
    <div class="sitem"><b>${fmtN(rows.length)}</b>Empresas filtradas</div>
    <div class="sitem"><b>${fmtN(iloc)}</b>Ilocalizables</div>
    <div class="sitem"><b>${fmtN(rows.filter(r=>estadoUnificado(r)==='Primer contacto').length)}</b>Primer contacto</div>
  `;
  const shown = rows.slice(0,400);
  document.getElementById('tblEmpresas').innerHTML = shown.map(r=>{
    const eu = estadoUnificado(r);
    const euCls = eu==='Ilocalizable' ? 'bad' : (eu==='Primer contacto' ? 'warn' : 'ok');
    return `<tr><td>${r.nom||'—'}</td><td>${r.nit||'—'}</td><td>${r.tam||'—'}</td><td>${r.ase||'—'}</td><td>${r.eq||'—'}</td>
    <td><span class="badge ${r.per==='No contactada'?'bad':(r.per==='Contactada - contrato actual'?'ok':'warn')}">${r.per}</span></td>
    <td>${r.dif}</td><td><span class="badge ${euCls}">${eu}</span></td><td>${r.fue||'—'}</td><td>${fmtN(gestionesPorNit[r.nit]||0)}</td></tr>`;
  }).join('') + (rows.length>400? `<tr><td colspan="10" style="text-align:center;color:var(--text-muted);font-style:italic;">Mostrando 400 de ${rows.length} — afina el filtro o exporta a Excel.</td></tr>`:'');
}'''
assert old_tbl_tail in final_html, "No se encontro el cierre de renderEmpresasAll (tabla + summary strip)"
final_html = final_html.replace(old_tbl_tail, new_tbl_tail)

# --- 9g-JS: listeners + export (unico, 1 sola hoja, mismo filtro de arriba) ---
old_export_tail = '''['fEmpBuscar'].forEach(id=>document.getElementById(id).addEventListener('input', renderEmpresasAll));
['fEmpPer','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif'].forEach(id=>document.getElementById(id).addEventListener('change', renderEmpresasAll));
document.getElementById('btnClearEmp').addEventListener('click',()=>{
  ['fEmpBuscar','fEmpPer','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif'].forEach(id=>document.getElementById(id).value='');
  renderEmpresasAll();
});
document.getElementById('btnExportEmp').addEventListener('click', ()=>{
  const rows = getEmpresasFiltered();
  exportToExcel(rows.map(r=>({Empresa:r.nom, NIT:r.nit, Tamaño:r.tam, Asesor:r.ase, Equipo:r.eq, 'Estado contacto':r.per, Dificultad:r.dif, Ilocalizable:r.iloc?'Sí':'No', 'Última gestión':r.fue||'', 'Estado afiliación':r.est, Sector:r.sec})), 'Empresas_CAJAMAG');
});
renderEmpresasAll();'''
new_export_tail = '''['fEmpBuscar'].forEach(id=>document.getElementById(id).addEventListener('input', renderEmpresasAll));
['fEmpPer','fEmpEstado','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif'].forEach(id=>document.getElementById(id).addEventListener('change', renderEmpresasAll));
document.getElementById('btnClearEmp').addEventListener('click',()=>{
  ['fEmpBuscar','fEmpPer','fEmpEstado','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif'].forEach(id=>document.getElementById(id).value='');
  renderEmpresasAll();
});
document.getElementById('btnExportEmp').addEventListener('click', ()=>{
  const rows = getEmpresasFiltered();
  exportToExcel(rows.map(r=>({
    Empresa:r.nom, NIT:r.nit, Tamaño:r.tam, Asesor:r.ase, Equipo:r.eq,
    'Estado contacto':r.per, Dificultad:r.dif, Estado:estadoUnificado(r),
    'Última gestión':r.fue||'', 'Estado afiliación':r.est, Sector:r.sec,
    'Teléfono':r.tel||'', 'Cantidad de gestiones':gestionesPorNit[r.nit]||0
  })), 'Empresas_CAJAMAG');
});
renderEmpresasAll();'''
assert old_export_tail in final_html, "No se encontro el bloque final de listeners/export de Empresas"
final_html = final_html.replace(old_export_tail, new_export_tail)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 9 aplicado: Empresas -- nueva variable 'Estado' (Ya se encontro/Primer contacto/Ilocalizable) reemplaza la columna Ilocalizable y las tarjetas separadas de Oportunidad/Ilocalizables; un unico filtro (arriba de Detalle de empresa) controla tabla, graficas y el Excel (ya no hay panel de filtro aparte para exportar); +Gestiones por empresa, +Telefono en el Excel.")

# ---------- 10. Hoja de Ventas (26-ago-2026, a pedido de Luis) ----------
# a) El campo 'servicio' crudo tiene 118 valores distintos porque mezcla el
#    servicio real con detalles/variantes/typos (ej. "IFT" y "Teyuna" aparecen
#    como si fueran servicios, cuando son variantes del mismo servicio oficial).
#    Luis mando una imagen con el catalogo OFICIAL de 29 servicios + su tarifa
#    de IVA. Se resuelve cada registro a su servicio oficial (por match directo,
#    por zona cuando el valor crudo viene "pelado" sin zona, o por palabras clave
#    de 'detalle' para el caso Teyuna que se parte en Cafeteria(8%) vs Centro
#    Recreacional(19%)). Con datos reales: 3480/3482 registros quedan
#    clasificados: 2 quedan como "Sin clasificar" (1 "SEGURO DE VIDA", que no
#    esta en el catalogo de Luis, y 1 registro con servicio=null y valor=0,
#    posible dato vacio/anulado) -- ambos se marcan explicitamente en vez de
#    forzarlos a una categoria que no les corresponde.
# b) Nuevo grafico de tendencia DIARIA (no solo mensual): usa el mes filtrado
#    arriba, o el mes mas reciente si no hay filtro de mes.
# c) Se quita la columna "Fuente" de la tabla y del Excel (Luis no quiere que
#    los asesores vean de donde vino cada dato).
# d) Se reordena la tabla/Excel: Asesor, Zona, Cedula/NIT, Cliente, Empresa,
#    Tipo de venta, Categoria, Servicio (oficial), Detalle, Fecha, Mes,
#    Cantidad, Valor, Valor sin IVA (calculado con la tarifa oficial de cada
#    servicio). "ID de venta" NO se agrega: no existe ningun identificador de
#    negocio/deal en 'transacciones' hoy -- se le informa a Luis por fuera del
#    codigo. "Categoria del cliente" tampoco existe a nivel de cliente/empresa
#    en este dataset -- se usa la 'categoria' (A-E) que ya trae cada
#    transaccion (categoria interna de servicio de la caja), dejando claro que
#    puede no ser exactamente lo que Luis tenia en mente.
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

# --- 10a-HTML: nueva tarjeta de tendencia diaria, entre Tendencia mensual y Ranking ---
old_tend_ranking = '''        <div class="chart-box"><canvas id="chVentasTendencia"></canvas></div>
      </div>
      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ranking de servicios — todos (según filtro)</span></div>'''
new_tend_ranking = '''        <div class="chart-box"><canvas id="chVentasTendencia"></canvas></div>
      </div>
      <div class="card">
        <div class="card-title"><span><span class="dot"></span><span id="ventasDiariaTitulo">Tendencia diaria</span></span></div>
        <div class="chart-box"><canvas id="chVentasDiaria"></canvas></div>
      </div>
      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ranking de servicios — todos (según filtro)</span></div>'''
assert old_tend_ranking in final_html, "No se encontro el anchor entre Tendencia mensual y Ranking de servicios"
final_html = final_html.replace(old_tend_ranking, new_tend_ranking)

# --- 10b-HTML: tabla de Detalle -> reordenar columnas, quitar Fuente, agregar Categoria/Valor sin IVA ---
old_tabla_ventas = '''        <table><thead><tr><th>Fecha</th><th>Mes</th><th>Asesor</th><th>Zona</th><th>Tipo</th><th>Servicio</th><th>Cliente</th><th>NIT/CC</th><th>Empresa</th><th>Detalle</th><th>Cantidad</th><th>Valor</th><th>Fuente</th></tr></thead><tbody id="tblVentas"></tbody></table>'''
new_tabla_ventas = '''        <table><thead><tr><th>Asesor</th><th>Zona</th><th>Cédula/NIT</th><th>Cliente</th><th>Empresa</th><th>Tipo</th><th>Categoría</th><th>Servicio</th><th>Detalle</th><th>Fecha</th><th>Mes</th><th>Cantidad</th><th>Valor</th><th>Valor sin IVA</th></tr></thead><tbody id="tblVentas"></tbody></table>'''
assert old_tabla_ventas in final_html, "No se encontro la tabla de Detalle de transacciones"
final_html = final_html.replace(old_tabla_ventas, new_tabla_ventas)

# --- 10c-JS: catalogo oficial de 29 servicios (imagen de Luis, 26-ago-2026) + resolucion por registro ---
old_populate_servicio = '''populateSelect('fVenServicio', ventasD.filtros.servicios);

let chVentasTendencia, chVentasServicio, chVentasTipo;'''
new_populate_servicio = '''// ---- Catálogo OFICIAL de servicios + IVA (imagen enviada por Luis, 26-ago-2026) ----
// El campo crudo 'servicio' mezcla el servicio real con detalles/variantes/typos
// (ej. "IFT" o "Teyuna" sueltos). Aquí se resuelve cada transacción a su
// servicio oficial y se calcula el valor sin IVA con la tarifa oficial.
const IMPUESTO_OFICIAL = {
  'ADULTO MAYOR': 19, 'VACUNACION SANTA MARTA': 0,
  'CAPACITACION SANTA MARTA': 19, 'CAPACITACION CIENAGA': 19, 'CAPACITACION FUNDACION': 19, 'CAPACITACION PIVIJAY': 19,
  'INST. FORMACION TECNICO': 0, 'INST. FORMACION TECN CIENAGA': 0, 'INST. FORMACION TECN FUNDACION': 0, 'INST. FORMACION TECNICO PIVIJA': 0,
  'CAP ESCUELA MUSICAL SANTA MARTA': 19, 'BIBLIOTECA SANTA MTA': 19, 'UNIDAD DE CULTURA Y COMUNICACION': 19, 'TEATRO CAJAMAG': 0,
  'RECREACION. STA MTA': 19, 'RECREACION CIENAGA': 19, 'RECREACION FUNDAC.': 19, 'CENTRO RECREC.TEYUNA': 19, 'CAFETERIA TEYUNA': 8,
  'DEPORTES STA MTA': 19, 'DEPORTES CIENAGA': 19, 'DEPORTES FUNDACION .': 19, 'RECREACION PIVIJAY': 19,
  'CENTRO RECREACIONAL CIENAGA': 19, 'CENTRO RECREACIONAL FUNDACION': 19,
  'TURISMO SOCIAL STA MARTA': 19, 'TURISMO SOCIAL CIENAGA': 19, 'TURISMO SOCIAL FUNDACION': 19, 'TURISMO SOCIAL PIVIJAY': 19,
};
function normServ(s){ return (s||'').toUpperCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').replace(/[^A-Z0-9]/g,''); }
const OFICIAL_NORM = {};
Object.keys(IMPUESTO_OFICIAL).forEach(k=>{ OFICIAL_NORM[normServ(k)] = k; });

const RECREACION_POR_ZONA = {'Santa Marta':'RECREACION. STA MTA','Ciénaga':'RECREACION CIENAGA','Fundación':'RECREACION FUNDAC.'};
const DEPORTES_POR_ZONA = {'Santa Marta':'DEPORTES STA MTA','Ciénaga':'DEPORTES CIENAGA','Fundación':'DEPORTES FUNDACION .'};
const CAPACITACION_POR_ZONA = {'Santa Marta':'CAPACITACION SANTA MARTA','Ciénaga':'CAPACITACION CIENAGA','Fundación':'CAPACITACION FUNDACION'};
const IFT_POR_ZONA = {'Santa Marta':'INST. FORMACION TECNICO','IFT':'INST. FORMACION TECNICO','Ciénaga':'INST. FORMACION TECN CIENAGA','Fundación':'INST. FORMACION TECN FUNDACION'};
const TURISMO_POR_ZONA = {'Santa Marta':'TURISMO SOCIAL STA MARTA','Ciénaga':'TURISMO SOCIAL CIENAGA','Fundación':'TURISMO SOCIAL FUNDACION'};
function porZonaServ(map, zona){ return map[zona] || map['Santa Marta']; }

const SERVICIO_RAW_FIJO = {
  'TEATRO CULPA':'TEATRO CAJAMAG','TEATRO- LOS DE LA CULPA':'TEATRO CAJAMAG','TEATRO CAJAMAG CULPA':'TEATRO CAJAMAG',
  'BOLETAS TEATRO ORQUESTA':'TEATRO CAJAMAG','BOLETA TEATRO ORQUETA ARANGO':'TEATRO CAJAMAG','boleta teatro orquesta':'TEATRO CAJAMAG',
  'TEATRO BOLETAS ORQUETAS':'TEATRO CAJAMAG','ENTRADAS ORQUESTA ARAGON':'TEATRO CAJAMAG','ENTRADAS TEATRO ORQUESTA ARAGON':'TEATRO CAJAMAG',
  'Teatro':'TEATRO CAJAMAG', 'Biblioteca':'BIBLIOTECA SANTA MTA',
  'Vacunación':'VACUNACION SANTA MARTA','VACUNA HEPATITIS A':'VACUNACION SANTA MARTA','VACUNA HEPATITIS B':'VACUNACION SANTA MARTA',
  'VACUNA MENINGOCOCO':'VACUNACION SANTA MARTA','HEPATITIS B PLENA':'VACUNACION SANTA MARTA','TETANO PLENA':'VACUNACION SANTA MARTA',
  'SERVICIOS UIS CIENAGA':'CAPACITACION CIENAGA','SERVICIOS UIS FUNDACION':'CAPACITACION FUNDACION',
};
['CURSO DE NATACION ADULTO INICIO','CURSO DE NATACION INICIO ADULTOS','CURSO DE NATACION INICIACION','ALQUILER DE CANCHA','Deporte']
  .forEach(k=>SERVICIO_RAW_FIJO[k]='__DEPORTES_ZONA__');
['CARIBE AVENTURA NIÑO','CARIBE AVENTURA ADULTO','CARIBE AVENTURA PASADIA','CUPO ADULTO CARIBE AVENTURA','NOCHE BLANCA KATAMARAN',
 'PASADIA ACUARIO','CAMINATA ECOLOGICA','CAMINATA ECOLOGICA INCA','PARQUE INFLAMBLE','PARQUE TEMATICO INFLABLE','CHIVA RUMBERA',
 'tradición de Cuba','SALIDAS PEDAGÓGICAS','ALQUILER DE SALON','ALQUILER DE AUDITORIO','ALQUILER DE SLAON X 4 HORAS','Alquiler de salones','Recreación']
  .forEach(k=>SERVICIO_RAW_FIJO[k]='__RECREACION_ZONA__');
['PLAN DECAMERON NIÑO','PLAN DECAMERON ADULTO','PLAN TURISTICO CARTAGENA','PASADIA BARRANQUILLA','SEGURO DE VIDA']
  .forEach(k=>SERVICIO_RAW_FIJO[k]='__TURISMO_ZONA__');
['IFT','Inscripción','Inglés conversacional'].forEach(k=>SERVICIO_RAW_FIJO[k]='__IFT_ZONA__');
[ 'CINEMARK','BOLETAS CINEMARK','COMBO CINE','combo de cine mark','combo cine','BONOS CINEMARK','ENTRADAS A CINEMARK','combo cine mark',
  'BONOS DE CINEMARK','combo de cine','BONOS PARA CINEMARK','Combo de cine mark','boletas cinemark','BOLETA CINEMARK','BONO CINEMARK','Bono Cinemark',
  'cinemark','CIBNEMARK','ENTRADAS A CINEMAK','combo de cinemark','comvo de cine mark','combo de cinemak','CINEMARK2','CINE COMBO',
  'boleta cine','BOLETAS DE CINE','Boleta de cine','ENTREDA CINEMAKR','ENTRADAS CINEMARK','ENTRADAS CINEMAKR','ENTRADA CINEMARK','bono de cinemark',
  'Combo de cine' ].forEach(k=>SERVICIO_RAW_FIJO[k]='__RECREACION_ZONA__');
const TEYUNA_CAFE_KEYWORDS = ['aliment','bebida','cafeteria','gaseosa','almuerzo','refrigerio','perro caliente','parrillada','botellon','mesero'];
['ALIMENTOS Y BEBIDAS TEYUNA','BOTELLON DE AGUA','GASEOSA','ALMUERZO INFANTIL','ALMUERZO PARRILLADA ADULTOS','REGRIGERIO PERRO CALIENTE RANCHERO','MESERO']
  .forEach(k=>SERVICIO_RAW_FIJO[k]='CAFETERIA TEYUNA');
['Teyuna','ALOJAMIENTO Y EVENTOS TEYUNA','Paasadia a teyuna','ALQUILER DE KIOSKI','KIOSCO X 8 HORAS','SALON PARA CAPACITACION TEYUNA']
  .forEach(k=>{ SERVICIO_RAW_FIJO[k]='__TEYUNA_KEYWORD__'; });

function resolverServicioOficial(r){
  const raw = r.servicio;
  const nrm = normServ(raw);
  if (OFICIAL_NORM[nrm]) return OFICIAL_NORM[nrm];
  const marker = SERVICIO_RAW_FIJO[raw];
  if (marker && !marker.startsWith('__')) return marker;
  if (marker === '__DEPORTES_ZONA__') return porZonaServ(DEPORTES_POR_ZONA, r.zona);
  if (marker === '__RECREACION_ZONA__') return porZonaServ(RECREACION_POR_ZONA, r.zona);
  if (marker === '__TURISMO_ZONA__') return porZonaServ(TURISMO_POR_ZONA, r.zona);
  if (marker === '__IFT_ZONA__') return porZonaServ(IFT_POR_ZONA, r.zona);
  if (marker === '__TEYUNA_KEYWORD__'){
    const d = (r.detalle||'').toLowerCase();
    const esComida = TEYUNA_CAFE_KEYWORDS.some(kw=>d.includes(kw));
    return esComida ? 'CAFETERIA TEYUNA' : 'CENTRO RECREC.TEYUNA';
  }
  return null; // sin clasificar (no aparece en el catálogo oficial de Luis)
}
ventasD.transacciones.forEach(r=>{
  const oficial = resolverServicioOficial(r);
  r.servicio_oficial = oficial || 'Sin clasificar (revisar)';
  r.impuesto_pct = oficial ? (IMPUESTO_OFICIAL[oficial]||0) : null;
  r.valor_sin_iva = r.impuesto_pct!=null ? Math.round(r.valor/(1+r.impuesto_pct/100)) : null;
});

populateSelect('fVenServicio', [...new Set(ventasD.transacciones.map(r=>r.servicio_oficial))].sort());

let chVentasTendencia, chVentasServicio, chVentasTipo, chVentasDiaria;'''
assert old_populate_servicio in final_html, "No se encontro populateSelect fVenServicio"
final_html = final_html.replace(old_populate_servicio, new_populate_servicio)

# --- 10d-JS: filtro por servicio ahora usa el oficial ---
old_filtro_servicio = '''  if (servicio) rows = rows.filter(r=>r.servicio===servicio);'''
new_filtro_servicio = '''  if (servicio) rows = rows.filter(r=>r.servicio_oficial===servicio);'''
assert old_filtro_servicio in final_html, "No se encontro el filtro de servicio"
final_html = final_html.replace(old_filtro_servicio, new_filtro_servicio)

# --- 10e-JS: ranking de servicios agrupado por el oficial ---
old_ranking_serv = '''  const servMap = {};
  rows.forEach(r=>{ servMap[r.servicio] = (servMap[r.servicio]||0) + r.valor; });'''
new_ranking_serv = '''  const servMap = {};
  rows.forEach(r=>{ servMap[r.servicio_oficial] = (servMap[r.servicio_oficial]||0) + r.valor; });'''
assert old_ranking_serv in final_html, "No se encontro el ranking de servicios"
final_html = final_html.replace(old_ranking_serv, new_ranking_serv)

# --- 10f-JS: tendencia diaria (nuevo grafico) ---
old_ranking_block_start = '''  // ---- Ranking de servicios (dentro del filtro) — todos los servicios ----'''
new_ranking_block_start = '''  // ---- Tendencia diaria (mes filtrado, o el mes más reciente si no hay filtro) ----
  const mesSel = document.getElementById('fVenMes').value;
  let ymFoco = mesSel ? ventasD.meses_order.find(ym=>ventasD.mes_labels[ym]===mesSel) : null;
  if (!ymFoco) ymFoco = ventasD.meses_order[ventasD.meses_order.length-1];
  const rowsDia = rows.filter(r=>r.ym===ymFoco);
  const porDia = {};
  rowsDia.forEach(r=>{ const d = (r.fecha||'').slice(8,10); if(!d) return; porDia[d] = (porDia[d]||0) + r.valor; });
  const diasOrden = Object.keys(porDia).sort((a,b)=>+a-+b);
  const diaVals = diasOrden.map(d=>porDia[d]);
  const labelMesFoco = ventasD.mes_labels[ymFoco] || ymFoco;
  document.getElementById('ventasDiariaTitulo').textContent = 'Tendencia diaria — ' + labelMesFoco + (mesSel? '' : ' (mes más reciente — filtra por mes arriba para ver otro)');
  if (!chVentasDiaria){
    chVentasDiaria = new Chart(document.getElementById('chVentasDiaria'),{
      type:'line', data:{ labels: diasOrden, datasets:[{label:'Venta del día', data: diaVals, borderColor:'#FF6900', backgroundColor:'#FF690033', tension:.3, fill:true, pointRadius:2}] },
      options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{y:{ticks:{callback:v=>(v/1000000)+'M'}}}}
    });
  } else {
    chVentasDiaria.data.labels = diasOrden;
    chVentasDiaria.data.datasets[0].data = diaVals;
    chVentasDiaria.update();
  }

  // ---- Ranking de servicios (dentro del filtro) — todos los servicios ----'''
assert old_ranking_block_start in final_html, "No se encontro el inicio del bloque de ranking de servicios"
final_html = final_html.replace(old_ranking_block_start, new_ranking_block_start)

# --- 10g-JS: tabla Detalle -> reordenar, quitar Fuente, +Categoria/+Valor sin IVA ---
old_tbl_ventas_js = '''  document.getElementById('tblVentas').innerHTML = shown.map(r=>`
    <tr><td>${r.fecha||'—'}</td><td>${ventasD.mes_labels[r.ym]||r.ym}</td><td>${r.asesor}</td><td>${r.zona||'—'}</td><td>${r.tipo_venta}</td><td>${r.servicio}</td><td>${r.cliente||'—'}</td><td>${r.nit||'—'}</td><td>${r.empresa||'—'}</td><td>${r.detalle||'—'}</td><td>${r.cantidad!=null?r.cantidad:'—'}</td><td>${fmt(r.valor)}</td><td>${r.fuente}</td></tr>
  `).join('') + (sorted.length>400? `<tr><td colspan="13" style="text-align:center;color:var(--text-muted);font-style:italic;">Mostrando 400 de ${sorted.length} — afina el filtro para ver el resto (o exporta a Excel).</td></tr>`:'');'''
new_tbl_ventas_js = '''  document.getElementById('tblVentas').innerHTML = shown.map(r=>`
    <tr><td>${r.asesor}</td><td>${r.zona||'—'}</td><td>${r.nit||'—'}</td><td>${r.cliente||'—'}</td><td>${r.empresa||'—'}</td><td>${r.tipo_venta}</td><td>${r.categoria||'—'}</td><td>${r.servicio_oficial}</td><td>${r.detalle||'—'}</td><td>${r.fecha||'—'}</td><td>${ventasD.mes_labels[r.ym]||r.ym}</td><td>${r.cantidad!=null?r.cantidad:'—'}</td><td>${fmt(r.valor)}</td><td>${r.valor_sin_iva!=null?fmt(r.valor_sin_iva):'—'}</td></tr>
  `).join('') + (sorted.length>400? `<tr><td colspan="14" style="text-align:center;color:var(--text-muted);font-style:italic;">Mostrando 400 de ${sorted.length} — afina el filtro para ver el resto (o exporta a Excel).</td></tr>`:'');'''
assert old_tbl_ventas_js in final_html, "No se encontro el render de tblVentas"
final_html = final_html.replace(old_tbl_ventas_js, new_tbl_ventas_js)

# --- 10h-JS: Excel -> mismo reorden, quitar Fuente, +Categoria/+Valor sin IVA ---
old_export_ventas = '''document.getElementById('btnExportVen').addEventListener('click',()=>{
  const rows = getVentasFiltered();
  const data = rows.map(r=>({
    Fecha: r.fecha, Mes: ventasD.mes_labels[r.ym]||r.ym, Asesor: r.asesor, Zona: r.zona||'—',
    'Tipo de venta': r.tipo_venta, Servicio: r.servicio, Categoría: r.categoria,
    Cliente: r.cliente||'', 'NIT/CC': r.nit||'', Empresa: r.empresa||'', Detalle: r.detalle||'', Cantidad: r.cantidad!=null?r.cantidad:'',
    Valor: r.valor, Fuente: r.fuente,
  }));
  exportToExcel(data, 'Ventas_CAJAMAG');
});'''
new_export_ventas = '''document.getElementById('btnExportVen').addEventListener('click',()=>{
  const rows = getVentasFiltered();
  const data = rows.map(r=>({
    Asesor: r.asesor, Zona: r.zona||'—', 'Cédula/NIT': r.nit||'', Cliente: r.cliente||'', Empresa: r.empresa||'',
    'Tipo de venta': r.tipo_venta, Categoría: r.categoria||'', Servicio: r.servicio_oficial, Detalle: r.detalle||'',
    Fecha: r.fecha, Mes: ventasD.mes_labels[r.ym]||r.ym, Cantidad: r.cantidad!=null?r.cantidad:'',
    Valor: r.valor, 'Valor sin IVA': r.valor_sin_iva!=null?r.valor_sin_iva:'',
  }));
  exportToExcel(data, 'Ventas_CAJAMAG');
});'''
assert old_export_ventas in final_html, "No se encontro el export de Ventas"
final_html = final_html.replace(old_export_ventas, new_export_ventas)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 10 aplicado: Ventas -- servicio normalizado al catalogo oficial (29 servicios + IVA), tendencia diaria, tabla/Excel reordenados sin Fuente, +Valor sin IVA.")

# ---------- 11. Ultimos Hechos: ventas auditadas + cambios de asesor (26-ago-2026, a pedido de Luis) ----------
# Luis pidio, sin tocar lo que ya habia en Ultimos Hechos (que se dejo igual
# desde el principio a peticion suya), agregar dos cosas nuevas que hoy SOLO
# viven en Supabase (no estan en el DATA blob del pipeline, asi que no pueden
# salir de 'raw_gestiones' -- se traen en vivo por fetch, igual que el widget
# 'EN VIVO' que ya existia (retirado como flotante, pero el patron de fetch a
# Supabase con la anon key sigue siendo el mismo, ya probado en produccion):
#   a) "Ventas auditadas": lee bitrix_eventos (estado_auditoria: pendiente/
#      aprobado/rechazado, + motivo_rechazo cuando aplica). Se filtra a
#      titulo no nulo porque hay filas "esqueleto" del webhook que aun no se
#      han enriquecido (eso pasa cuando alguien abre la app de auditoria).
#   b) "Cambios de asesor en empresas": lee empresas_cambios_asesor (ya tiene
#      al menos 1 caso real: UNIVERSAL GAS S A S, de Cristina Ahumada a
#      Oriana Yadith Felizzola). Esta tabla la alimenta el enriquecimiento de
#      webhook_enrich_widget.py que ya corre en segundo plano en este mismo
#      archivo -- aqui solo se agrega la parte visible (antes no habia UI).
# Ambas tarjetas se refrescan solas cada 45s mientras el dashboard este abierto.
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

# --- 11a-HTML: 2 tarjetas nuevas al final de Ultimos Hechos ---
old_hechos_feed_card = '''      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Feed de actividad reciente (últimas 100)</span></div>
        <div class="table-scroll">
        <table><thead><tr><th>Fecha</th><th>Asesor</th><th>Empresa</th><th>NIT</th><th>Medio</th><th>Gestión</th><th>Comentario</th></tr></thead><tbody id="tblHechosFeed"></tbody></table>
        </div>
      </div>
    </section>'''
new_hechos_feed_card = '''      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Feed de actividad reciente (últimas 100)</span></div>
        <div class="table-scroll">
        <table><thead><tr><th>Fecha</th><th>Asesor</th><th>Empresa</th><th>NIT</th><th>Medio</th><th>Gestión</th><th>Comentario</th></tr></thead><tbody id="tblHechosFeed"></tbody></table>
        </div>
      </div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ventas auditadas (en vivo)</span></div>
        <div class="section-desc">Estado de auditoría de las ventas registradas en Bitrix — se refresca solo cada 45 segundos.</div>
        <div class="table-scroll">
        <table><thead><tr><th>Fecha</th><th>Asesor</th><th>Negocio</th><th>Monto</th><th>Estado</th><th>Motivo de rechazo</th></tr></thead><tbody id="tblVentasAuditadas"><tr><td colspan="6" style="text-align:center;color:var(--text-muted);font-style:italic;">Cargando…</td></tr></tbody></table>
        </div>
      </div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Cambios de asesor en empresas (en vivo)</span></div>
        <div class="section-desc">Reasignaciones de empresa detectadas automáticamente al comparar el responsable actual en Bitrix contra el último registrado.</div>
        <div class="table-scroll">
        <table><thead><tr><th>Detectado</th><th>Empresa</th><th>Asesor anterior</th><th>Asesor nuevo</th></tr></thead><tbody id="tblCambiosAsesor"><tr><td colspan="4" style="text-align:center;color:var(--text-muted);font-style:italic;">Cargando…</td></tr></tbody></table>
        </div>
      </div>
    </section>'''
assert old_hechos_feed_card in final_html, "No se encontro la tarjeta de Feed de actividad reciente"
final_html = final_html.replace(old_hechos_feed_card, new_hechos_feed_card)

# --- 11b-JS: fetch en vivo a Supabase (misma anon key ya usada en live_widget.py / webhook_enrich_widget.py) ---
old_hechos_js_end = '''  document.getElementById('tblHechosFeed').innerHTML = raw.slice(0,100).map(r=>`
    <tr><td>${r.fecha}</td><td>${r.asesor}</td><td>${r.empresa||'—'}</td><td>${r.nit||'—'}</td><td>${r.medio||'—'}</td><td>${r.gestion||'—'}</td><td>${r.comentario||'—'}</td></tr>
  `).join('');
})();'''
new_hechos_js_end = '''  document.getElementById('tblHechosFeed').innerHTML = raw.slice(0,100).map(r=>`
    <tr><td>${r.fecha}</td><td>${r.asesor}</td><td>${r.empresa||'—'}</td><td>${r.nit||'—'}</td><td>${r.medio||'—'}</td><td>${r.gestion||'—'}</td><td>${r.comentario||'—'}</td></tr>
  `).join('');
})();

// ---- Ventas auditadas + Cambios de asesor (en vivo via Supabase, 26-ago-2026 a pedido de Luis) ----
(function(){
  const SUPA_URL = 'https://nzmnzmnozbeqttofbmlf.supabase.co';
  const SUPA_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im56bW56bW5vemJlcXR0b2ZibWxmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk2NTAzMjQsImV4cCI6MjA5NTIyNjMyNH0.r3hrXsazoJK_xUWTsskEgjQ40Xhg60_0YaGvWs1VXP8';
  function fmtMoneyH(n){ if(n==null) return '—'; return '$'+Math.round(n).toLocaleString('es-CO'); }
  function fmtFechaH(iso){ if(!iso) return '—'; try{ const d=new Date(iso); return d.toLocaleDateString('es-CO')+' '+d.toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'}); }catch(e){ return iso; } }
  function estadoBadgeH(e){
    if(e==='aprobado') return '<span class="badge ok">Aprobado</span>';
    if(e==='rechazado') return '<span class="badge bad">Rechazado</span>';
    return '<span class="badge warn">Pendiente</span>';
  }
  function cargarVentasAuditadas(){
    fetch(SUPA_URL+'/rest/v1/bitrix_eventos?evento=neq.backfill_historico&titulo=not.is.null&order=creado_en.desc&limit=60', {
      headers:{apikey:SUPA_ANON, Authorization:'Bearer '+SUPA_ANON}
    }).then(r=>r.json()).then(rows=>{
      const tbl = document.getElementById('tblVentasAuditadas');
      if(!tbl) return;
      if(!Array.isArray(rows) || !rows.length){ tbl.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);font-style:italic;">Sin ventas registradas todavía.</td></tr>'; return; }
      tbl.innerHTML = rows.map(r=>`
        <tr><td>${fmtFechaH(r.creado_en)}</td><td>${r.asesor||'—'}</td><td>${r.titulo||('Negocio '+r.deal_id)}</td><td>${fmtMoneyH(r.monto)}</td><td>${estadoBadgeH(r.estado_auditoria)}</td><td>${r.motivo_rechazo||'—'}</td></tr>
      `).join('');
    }).catch(e=>console.error('ventas auditadas error', e));
  }
  function cargarCambiosAsesor(){
    fetch(SUPA_URL+'/rest/v1/empresas_cambios_asesor?order=detectado_en.desc&limit=60', {
      headers:{apikey:SUPA_ANON, Authorization:'Bearer '+SUPA_ANON}
    }).then(r=>r.json()).then(rows=>{
      const tbl = document.getElementById('tblCambiosAsesor');
      if(!tbl) return;
      if(!Array.isArray(rows) || !rows.length){ tbl.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted);font-style:italic;">Sin cambios de asesor detectados todavía.</td></tr>'; return; }
      tbl.innerHTML = rows.map(r=>`
        <tr><td>${fmtFechaH(r.detectado_en)}</td><td>${r.nombre_empresa||'—'}</td><td>${r.asesor_anterior_nombre||'—'}</td><td>${r.asesor_nuevo_nombre||'—'}</td></tr>
      `).join('');
    }).catch(e=>console.error('cambios asesor error', e));
  }
  function cicloHechosVivo(){ cargarVentasAuditadas(); cargarCambiosAsesor(); }
  cicloHechosVivo();
  setInterval(cicloHechosVivo, 45000);
})();'''
assert old_hechos_js_end in final_html, "No se encontro el final del IIFE de Ultimos Hechos"
final_html = final_html.replace(old_hechos_js_end, new_hechos_js_end)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 11 aplicado: Ultimos Hechos -- +Ventas auditadas (en vivo) y +Cambios de asesor en empresas (en vivo), ambas via Supabase, sin tocar lo que ya habia.")

# ---------- 12. Historia Comercial del Asesor (27-ago-2026, a pedido de Luis) ----------
# Pedido (mensaje dictado, 9 puntos -- el punto 9 queda diferido, lo dijo el mismo Luis):
#  1) Quitar tarjeta "Ventas efectivas ($)" del grid de indicadores (siempre "sin dato").
#  2) Tab "Ejecutado Mar-Jul" -> "Ejecutado" (aqui se habla de todos los meses, no de un rango fijo).
#  3) Quitar tarjeta "Ordenes de matricula" del grid (por el momento).
#  4) Agregar tarjetas de "Medios de contacto" (con sus metas) despues de Gestion vs. metas.
#     CORREGIDO (27-ago-2026 x3, Luis senalo que SI hay meta individual para los otros 4
#     medios -- "la tienes en el tablero por mes"): en pipeline_master.py (CANAL_TARGETS,
#     confirmado por Luis 25-ago-2026) cada asesor SI tiene una meta MENSUAL real para
#     Llamadas/WhatsApp/Correos/Reuniones virtuales, segun su zona (Call Center/Santa Marta/
#     Ciénaga/Fundación) -- es la misma meta que ya se ve en el Tablero TV (fila de canales de
#     "Gestión Comercial"). Aqui se porta ese mismo CANAL_TARGETS y se prorratea por los meses
#     activos del asesor (o el mes puntual, si el filtro esta en un mes especifico) para que
#     Historia Comercial muestre exactamente la misma meta que el Tablero, no una referencia.
#     Visitas presenciales sigue usando su propia meta individual ya prorateada por el pipeline
#     (igual que antes). Como Visitas presenciales ya es uno de los 5 medios, se saca del grid
#     general de indicadores (para no repetirla dos veces) y se muestra solo aqui, junto a los
#     otros 4.
#  5) Grafico "Por tipo de venta": de conteo de transacciones a valor vendido ($) Individual vs Empresarial.
#  6) "Servicios mas vendidos": agrupar por servicio_oficial (catalogo normalizado del Paso 10),
#     no por el "servicio" crudo -- mismo fix que ya se aplico en la hoja Ventas.
#  7) Cadencia: +linea de tendencia de "medio de contacto" (volumen total de gestiones por los
#     5 medios oficiales, por mes), ademas de Gestion/Bitrix y Ventas que ya estaban.
#  8) Nueva tarjeta "Empresas por gestionar" (empresas nunca contactadas en este contrato) entre
#     el resumen de Empresas y el Top 10 no atendidas, con 4 mini-tarjetas por tamaño.
#  9) DIFERIDO por el propio Luis: revisar el sistema de actualizacion del Top 10 no atendidas
#     -- "luego que terminemos los dashboard alli veremos". No se toca aqui.
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

# --- 12a-HTML: nueva tarjeta "Medios de contacto" despues de "Gestion vs. metas", antes de "Ventas" ---
old_hca_medios_anchor = '''        <div class="hca-ind-grid" id="hcaIndicadoresGrid"></div>
      </div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>💰 Ventas</span></div>'''
new_hca_medios_anchor = '''        <div class="hca-ind-grid" id="hcaIndicadoresGrid"></div>
      </div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>📞 Medios de contacto</span></div>
        <div class="section-desc">Real vs. meta mensual por canal, según la zona del asesor (Call Center / Santa Marta / Ciénaga / Fundación) — la misma meta que ya se ve en el Tablero TV.</div>
        <div class="hca-ind-grid" id="hcaMediosGrid"></div>
      </div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>💰 Ventas</span></div>'''
assert old_hca_medios_anchor in final_html, "No se encontro el anchor de Medios de contacto en Historia"
final_html = final_html.replace(old_hca_medios_anchor, new_hca_medios_anchor)

# --- 12b-HTML: (corregido 27-ago x2, a pedido de Luis) el desglose por tamaño no va como
# bloque aparte debajo de las 4 tarjetas -- va PEGADO dentro de cada una de las 4 tarjetas
# (Asignadas/Gestionadas/Oportunidad/Ilocalizables), como 4 mini-tarjetas horizontales del
# mismo color que la tarjeta que las contiene. Por eso las 4 tarjetas dejan de ser divs sueltos
# en un kpi-grid comun -- ahora cada una se arma completa (numero + su propio mini-grid de
# tamaño) en el JS, y aqui solo queda un contenedor.
old_hca_emp_anchor = '''        <div class="kpi-grid" id="hcaEmpresasKpis"></div>
      </div>

      <div class="card pdf-own-page" id="hcaEmpresasListCard">'''
new_hca_emp_anchor = '''        <div class="kpi-grid" id="hcaEmpresasKpis"></div>
      </div>

      <div class="card pdf-own-page" id="hcaEmpresasListCard">'''
assert old_hca_emp_anchor in final_html, "No se encontro el anchor de hcaEmpresasKpis"
final_html = final_html.replace(old_hca_emp_anchor, new_hca_emp_anchor)

# --- 12c-JS: tab "ACC" de Historia -> "Ejecutado" (sin rango fijo) ---
old_hca_acc_tab = '''  let html = `<div class="month-tab accent ${hcaPeriod==='ACC'?'active':''}" data-period="ACC">Ejecutado Mar–Jul</div>`;'''
new_hca_acc_tab = '''  let html = `<div class="month-tab accent ${hcaPeriod==='ACC'?'active':''}" data-period="ACC">Ejecutado</div>`;'''
assert old_hca_acc_tab in final_html, "No se encontro el tab ACC de Historia"
final_html = final_html.replace(old_hca_acc_tab, new_hca_acc_tab)

old_hca_periodlabel = '''  const periodLabel = hcaPeriod==='ACC' ? 'Ejecutado Mar–Jul' : DATA.gestiones.month_labels[hcaPeriod];'''
new_hca_periodlabel = '''  const periodLabel = hcaPeriod==='ACC' ? 'Ejecutado' : DATA.gestiones.month_labels[hcaPeriod];'''
assert old_hca_periodlabel in final_html, "No se encontro periodLabel de Historia"
final_html = final_html.replace(old_hca_periodlabel, new_hca_periodlabel)

# --- 12d-JS: grid de indicadores -> quitar Ventas efectivas ($), Ordenes de matricula y Visitas presenciales (se va a Medios) ---
old_gridinds = '''  const gridInds = periodData ? Object.entries(periodData.indicators) : [];'''
new_gridinds = '''  const HCA_GRID_EXCLUDE = ['Ventas efectivas ($)','Órdenes de matrícula','Visitas presenciales'];
  const gridInds = periodData ? Object.entries(periodData.indicators).filter(([k])=>!HCA_GRID_EXCLUDE.includes(k)) : [];'''
assert old_gridinds in final_html, "No se encontro gridInds de Historia"
final_html = final_html.replace(old_gridinds, new_gridinds)

# --- 12e-JS: tarjetas de Medios de contacto (real + meta individual real para los 5 medios,
# igual que en el Tablero TV: CANAL_TARGETS de pipeline_master.py, meta mensual por zona) ---
old_medios_insert_anchor = '''  }).join('');

  // ---- Ventas (recalculadas desde transacciones por asesor + periodo) ----'''
new_medios_insert_anchor = '''  }).join('');

  // ---- Medios de contacto (real desde bitácora de gestiones + meta individual real, misma
  // regla que el Tablero TV: CANAL_TARGETS por zona del asesor, confirmada por Luis 25-ago-2026) ----
  const MEDIO_RAW_TO_OFICIAL = {'Llamada':'Llamadas','WhatsApp':'WhatsApp','Correo electrónico':'Correos','Visita presencial':'Visitas presenciales','Reunión virtual':'Reunión virtual'};
  const rawGesAsesor = (DATA.gestiones.raw_gestiones||[]).filter(r=>r.asesor===name && (hcaPeriod==='ACC' || (r.fecha||'').slice(0,7)===hcaPeriod));
  const medioRealAsesor = {};
  rawGesAsesor.forEach(r=>{ const k = MEDIO_RAW_TO_OFICIAL[r.medio]; if(k) medioRealAsesor[k] = (medioRealAsesor[k]||0)+1; });
  const medioCatContrato = (contract.categories.find(c=>c.name==='Medios de contacto')||{indicators:[]}).indicators;
  const CANAL_TARGETS = {
    'Llamadas': {'Call Center':300,'Santa Marta':100,'Ciénaga':70,'Fundación':60},
    'WhatsApp': {'Call Center':400,'Santa Marta':120,'Ciénaga':90,'Fundación':70},
    'Correos': {'Call Center':150,'Santa Marta':70,'Ciénaga':50,'Fundación':40},
    'Reunión virtual': {'Call Center':4,'Santa Marta':3,'Ciénaga':2,'Fundación':2},
  };
  function zonaEnMes(ym){ const md = a.months[ym]; return (md && md.perfil) || a.current_profile || 'Sin zona'; }
  const mesesMedios = hcaPeriod==='ACC' ? (a.active_months||[]) : (a.months[hcaPeriod] ? [hcaPeriod] : []);
  document.getElementById('hcaMediosGrid').innerHTML = medioCatContrato.map(mi=>{
    const real = medioRealAsesor[mi.name]||0;
    const dVis = periodData ? periodData.indicators['Visitas presenciales'] : null;
    if (mi.name==='Visitas presenciales' && dVis && !dVis.na){
      const pct = dVis.pct*100, cls = statusClass(pct), fillCls = cls===''?'ok':cls;
      return `<div class="hca-ind-card"><div class="hi-top"><span class="hi-name">${mi.name}</span><span class="hi-pct">${pct.toFixed(0)}%</span></div>
        <div class="hi-track"><div class="hi-fill ${fillCls}" style="width:${Math.min(pct,100)}%"></div></div>
        <div class="hi-meta">${dVis.real} / ${dVis.meta} meta</div></div>`;
    }
    const tgt = CANAL_TARGETS[mi.name];
    const meta = tgt ? mesesMedios.reduce((s,ym)=> s + (tgt[zonaEnMes(ym)] || 0), 0) : 0;
    if (meta>0){
      const pct = real/meta*100, cls = statusClass(pct), fillCls = cls===''?'ok':cls;
      return `<div class="hca-ind-card"><div class="hi-top"><span class="hi-name">${mi.name}</span><span class="hi-pct">${pct.toFixed(0)}%</span></div>
        <div class="hi-track"><div class="hi-fill ${fillCls}" style="width:${Math.min(pct,100)}%"></div></div>
        <div class="hi-meta">${real} / ${meta} meta</div></div>`;
    }
    return `<div class="hca-ind-card"><div class="hi-top"><span class="hi-name">${mi.name}</span><span class="hi-pct" style="color:#9AA1B0;">${real}</span></div>
      <div class="hi-meta">Sin meta aplicable (zona sin meta definida en este periodo)</div></div>`;
  }).join('');

  // ---- Ventas (recalculadas desde transacciones por asesor + periodo) ----'''
assert old_medios_insert_anchor in final_html, "No se encontro el anchor para insertar Medios de contacto"
final_html = final_html.replace(old_medios_insert_anchor, new_medios_insert_anchor)

# --- 12f-JS: "Por tipo de venta" -> valor vendido ($) en vez de conteo de transacciones ---
old_tipo_venta_chart = '''  const tvCounts = {};
  ventasRows.forEach(t=>{ const k=t.tipo_venta||'Sin dato'; if(!tvCounts[k]) tvCounts[k]={n:0,valor:0}; tvCounts[k].n++; tvCounts[k].valor+=t.valor; });
  const tvLabels = Object.keys(tvCounts);
  const tvData = tvLabels.map(k=>tvCounts[k].n);
  if (!hcaChTipoVentaChart){
    hcaChTipoVentaChart = new Chart(document.getElementById('hcaChTipoVenta'),{
      type:'doughnut', data:{labels:tvLabels, datasets:[{data:tvData, backgroundColor:['#00685E','#FF6900','#D2CE9E','#B8B8B8']}]},
      options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}}
    });
  } else { hcaChTipoVentaChart.data.labels=tvLabels; hcaChTipoVentaChart.data.datasets[0].data=tvData; hcaChTipoVentaChart.update(); }'''
new_tipo_venta_chart = '''  const tvCounts = {};
  ventasRows.forEach(t=>{ const k=t.tipo_venta||'Sin dato'; if(!tvCounts[k]) tvCounts[k]={n:0,valor:0}; tvCounts[k].n++; tvCounts[k].valor+=t.valor; });
  const tvLabels = Object.keys(tvCounts);
  const tvData = tvLabels.map(k=>tvCounts[k].valor);
  if (!hcaChTipoVentaChart){
    hcaChTipoVentaChart = new Chart(document.getElementById('hcaChTipoVenta'),{
      type:'doughnut', data:{labels:tvLabels, datasets:[{data:tvData, backgroundColor:['#00685E','#FF6900','#D2CE9E','#B8B8B8']}]},
      options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{font:{size:10}}}, tooltip:{callbacks:{label:(ctx)=>ctx.label+': '+fmt(ctx.parsed)}}}}
    });
  } else { hcaChTipoVentaChart.data.labels=tvLabels; hcaChTipoVentaChart.data.datasets[0].data=tvData; hcaChTipoVentaChart.update(); }'''
assert old_tipo_venta_chart in final_html, "No se encontro el grafico Por tipo de venta"
final_html = final_html.replace(old_tipo_venta_chart, new_tipo_venta_chart)

# --- 12g-JS: "Servicios mas vendidos" -> agrupar por servicio_oficial (catalogo normalizado) ---
old_servicios_chart = '''  const svcCounts = {};
  ventasRows.forEach(t=>{ const k=t.servicio||'Sin dato'; if(!svcCounts[k]) svcCounts[k]={n:0,valor:0}; svcCounts[k].n++; svcCounts[k].valor+=t.valor; });'''
new_servicios_chart = '''  const svcCounts = {};
  ventasRows.forEach(t=>{ const k=t.servicio_oficial||'Sin clasificar (revisar)'; if(!svcCounts[k]) svcCounts[k]={n:0,valor:0}; svcCounts[k].n++; svcCounts[k].valor+=t.valor; });'''
assert old_servicios_chart in final_html, "No se encontro svcCounts de Servicios mas vendidos"
final_html = final_html.replace(old_servicios_chart, new_servicios_chart)

# --- 12h-JS: Cadencia -> +linea de tendencia de medio de contacto ---
old_cadencia_block = '''  const cadVentas = cadMonths.map(ym=> DATA.ventas.transacciones.filter(t=>t.asesor===name && t.ym===ym).length);
  if (!hcaChCadenciaChart){
    hcaChCadenciaChart = new Chart(document.getElementById('hcaChCadencia'),{
      type:'line', data:{labels:cadLabels, datasets:[
        {label:'Gestión / carga en Bitrix (actividades)', data:cadGestion, borderColor:'#00685E', backgroundColor:'#00685E33', tension:.3, fill:true},
        {label:'Ventas (transacciones)', data:cadVentas, borderColor:'#FF6900', backgroundColor:'#FF690033', tension:.3, fill:true},
      ]}, options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}}
    });
  } else { hcaChCadenciaChart.data.labels=cadLabels; hcaChCadenciaChart.data.datasets[0].data=cadGestion; hcaChCadenciaChart.data.datasets[1].data=cadVentas; hcaChCadenciaChart.update(); }'''
new_cadencia_block = '''  const cadVentas = cadMonths.map(ym=> DATA.ventas.transacciones.filter(t=>t.asesor===name && t.ym===ym).length);
  const cadMedios = cadMonths.map(ym=> (DATA.gestiones.raw_gestiones||[]).filter(r=>r.asesor===name && (r.fecha||'').slice(0,7)===ym && MEDIO_RAW_TO_OFICIAL[r.medio]).length);
  if (!hcaChCadenciaChart){
    hcaChCadenciaChart = new Chart(document.getElementById('hcaChCadencia'),{
      type:'line', data:{labels:cadLabels, datasets:[
        {label:'Gestión / carga en Bitrix (actividades)', data:cadGestion, borderColor:'#00685E', backgroundColor:'#00685E33', tension:.3, fill:true},
        {label:'Ventas (transacciones)', data:cadVentas, borderColor:'#FF6900', backgroundColor:'#FF690033', tension:.3, fill:true},
        {label:'Medios de contacto (llamadas+whatsapp+correos+visitas+reuniones)', data:cadMedios, borderColor:'#2E75B6', backgroundColor:'transparent', tension:.3, fill:false, borderDash:[5,3]},
      ]}, options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}}
    });
  } else { hcaChCadenciaChart.data.labels=cadLabels; hcaChCadenciaChart.data.datasets[0].data=cadGestion; hcaChCadenciaChart.data.datasets[1].data=cadVentas; hcaChCadenciaChart.data.datasets[2].data=cadMedios; hcaChCadenciaChart.update(); }'''
assert old_cadencia_block in final_html, "No se encontro el bloque de Cadencia"
final_html = final_html.replace(old_cadencia_block, new_cadencia_block)

# --- 12i-JS: (corregido 27-ago, a pedido de Luis) sin tarjeta nueva -- el desglose por tamaño
# va debajo de las 4 tarjetas de Empresas que ya existian, y esas 4 tarjetas se recalculan en
# vivo desde empresas_full (mismo filtro que la hoja Empresas) en vez del snapshot precomputado
# historia_asesor.empresas, que estaba desactualizado en 11 de 15 asesores (ej. Miguel David
# Alzate Vargas: "asignadas" mostraba 387, la cifra real hoy en empresas_full es 200 -- 187 de
# diferencia, probablemente por reasignaciones de asesor que ya se detectan en Ultimos Hechos).
old_empresas_kpis = '''  // ---- Empresas (estado actual, no varía por mes) ----
  const he = h.empresas || {};
  document.getElementById('hcaEmpresasKpis').innerHTML = `
    <div class="kpi"><div class="kv">${he.total_asignadas||0}</div><div class="kl">Empresas asignadas (Responsable)</div></div>
    <div class="kpi acc"><div class="kv">${he.gestionadas_actual||0}</div><div class="kl">Gestionadas este contrato</div></div>
    <div class="kpi warn"><div class="kv">${he.oportunidad_primer_contacto||0}</div><div class="kl">Oportunidad de primer contacto</div></div>
    <div class="kpi bad"><div class="kv">${he.ilocalizables||0}</div><div class="kl">Ilocalizables</div></div>
  `;

  const noContRows = empFull.filter(r=>r.ase===name && r.per==='No contactada')
    .sort((x,y)=> TAM_ORDER.indexOf(x.tam) - TAM_ORDER.indexOf(y.tam));
  const top10NoCont = noContRows.slice(0,10);'''
new_empresas_kpis = '''  // ---- Empresas (estado actual, no varía por mes; recalculado en vivo desde empresas_full) ----
  const heRows = empFull.filter(r=>r.ase===name);
  const heGestionadas = heRows.filter(r=>r.per==='Contactada - contrato actual');
  const heOportunidad = heRows.filter(r=>r.per==='No contactada');
  const heIloc = heRows.filter(r=>r.iloc);
  function hcaTamBreak(rows){
    const c = {'Grande':0,'Mediana':0,'Pequeña':0,'Micro':0};
    rows.forEach(r=>{ const t = (r.tam in c) ? r.tam : 'Micro'; c[t]++; });
    return c;
  }
  function hcaTamMiniRow(cls, rows){
    const c = hcaTamBreak(rows);
    const cell = (n,l)=>`<div class="kpi ${cls}" style="padding:6px 8px;border-top-width:2px;"><div class="kv" style="font-size:14px;">${n}</div><div class="kl" style="font-size:8.5px;">${l}</div></div>`;
    return `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:10px;">
      ${cell(c['Grande'],'Grande')}${cell(c['Mediana'],'Mediana')}${cell(c['Pequeña'],'Pequeña')}${cell(c['Micro'],'Micro')}
    </div>`;
  }
  document.getElementById('hcaEmpresasKpis').innerHTML = `
    <div class="kpi"><div class="kv">${heRows.length}</div><div class="kl">Empresas asignadas (Responsable)</div>${hcaTamMiniRow('', heRows)}</div>
    <div class="kpi acc"><div class="kv">${heGestionadas.length}</div><div class="kl">Gestionadas este contrato</div>${hcaTamMiniRow('acc', heGestionadas)}</div>
    <div class="kpi warn"><div class="kv">${heOportunidad.length}</div><div class="kl">Oportunidad de primer contacto</div>${hcaTamMiniRow('warn', heOportunidad)}</div>
    <div class="kpi bad"><div class="kv">${heIloc.length}</div><div class="kl">Ilocalizables</div>${hcaTamMiniRow('bad', heIloc)}</div>
  `;

  const noContRows = heOportunidad.slice().sort((x,y)=> TAM_ORDER.indexOf(x.tam) - TAM_ORDER.indexOf(y.tam));
  const top10NoCont = noContRows.slice(0,10);'''
assert old_empresas_kpis in final_html, "No se encontro el bloque original de hcaEmpresasKpis"
final_html = final_html.replace(old_empresas_kpis, new_empresas_kpis)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 12 aplicado: Historia Comercial -- quita 2 tarjetas 'Sin datos' + Visitas presenciales del grid general, tab 'Ejecutado', +Medios de contacto (real+meta/referencia), Por tipo de venta en $, Servicios mas vendidos normalizado, +linea de medio de contacto en Cadencia, +desglose por tamano debajo de las 4 tarjetas de Empresas (recalculadas en vivo desde empresas_full, corrige desactualizacion del snapshot historia_asesor en 11/15 asesores).")

# ---------- 13. Ventas: ocultar nota "Fuente combinada" (27-ago-2026, a pedido de Luis) ----------
# Luis: "no me genera valor" -- se oculta el cuadro tecnico de trazabilidad de fuentes
# (marzo-julio dataframe vs Bitrix IFT vs Panaca manual), que es info de auditoria interna,
# no algo que el asesor/coordinador necesite ver en pantalla. Se oculta via CSS (display:none)
# en vez de borrar la logica que la llena, por si se necesita reactivar rapido.
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()
old_ventas_nota = '''      <div class="note" id="ventasNota"></div>'''
new_ventas_nota = '''      <div class="note" id="ventasNota" style="display:none;"></div>'''
assert old_ventas_nota in final_html, "No se encontro el div ventasNota"
final_html = final_html.replace(old_ventas_nota, new_ventas_nota)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 13 aplicado: Ventas -- nota 'Fuente combinada' oculta (display:none), sin borrar la logica que la llena.")

# ---------- 14. Tabla "Ejecucion vs. meta -- Ventas (por asesor)": vuelve a Resumen (27-ago-2026, a pedido de Luis) ----------
# Luis, tras verla en Ventas, penso mejor y pidio que vuelva a Resumen (donde vivia antes del
# Paso 7), con 2 cambios:
#  1) Agregar Desde/Hasta (rango de meses activo), no solo el conteo.
#  2) La meta debe estar sujeta al tiempo real que estuvo el asesor -- NO medir igual a quien
#     estuvo 6 meses que a quien estuvo 2. Se encontro la causa raiz: el campo precalculado
#     meta_acumulada_5m usa un meses_activos propio (guardado en DATA.ventas.ranking en el
#     momento en que se calculo), que puede desincronizarse del meses_activos ACTUAL del
#     asesor (el mismo que se muestra en la columna "Meses activo", tomado de
#     gestiones.advisors_full) -- por eso, por ejemplo, Paulina Leonor Barros Manjarres
#     aparecia con solo 2 meses activos pero la MISMA meta total ($144.268.817) que asesoras
#     con 5 meses activos. La correccion: se recupera la tasa MENSUAL real de cada asesor
#     (meta_acumulada_5m / el meses_activos con que se calculo) y se multiplica por el
#     meses_activos ACTUAL (misma fuente que la columna visible), garantizando que meta y
#     "Meses activo" siempre queden consistentes entre si. Asesores sin ranking de ventas
#     (o sin meta) usan la tasa de "primer mes" ya establecida (21M/mes, confirmada por Luis
#     para Jessica Luque Garcia y Karen Liseth Cantillo De la Cruz).
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

# --- 14a-HTML: quitar la tarjeta de Ventas (vuelve el anchor a como estaba antes del Paso 7b) ---
old_ventas_card_out = '''      <div class="kpi-grid" id="ventasKpis"></div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ejecución vs. meta — Ventas (por asesor)</span></div>
        <div class="table-scroll">
        <table><thead><tr><th>Asesor</th><th>Meses activo</th><th>Ejecutado</th><th>Meta a la fecha</th><th>% Ejecución</th></tr></thead><tbody id="tblVentasEjecucionAsesor"></tbody></table>
        </div>
      </div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Tendencia mensual (según filtro)</span></div>'''
new_ventas_card_out = '''      <div class="kpi-grid" id="ventasKpis"></div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Tendencia mensual (según filtro)</span></div>'''
assert old_ventas_card_out in final_html, "No se encontro la tarjeta de Ventas a quitar"
final_html = final_html.replace(old_ventas_card_out, new_ventas_card_out)

# --- 14b-HTML: agregar la tarjeta a Resumen, con Desde/Hasta ---
old_resumen_close = '''      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ejecución de Gestión (equipo) — por frente de contrato</span></div>
        <div class="kpi-grid" id="resumenGestionEquipo"></div>
      </div>
    </section>'''
new_resumen_close = '''      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ejecución de Gestión (equipo) — por frente de contrato</span></div>
        <div class="kpi-grid" id="resumenGestionEquipo"></div>
      </div>

      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ejecución de Ventas (por asesor)</span></div>
        <div class="section-desc">Ordenado de mayor a menor por lo ejecutado. % Participación = qué parte del total vendido por el equipo aporta cada asesor.</div>
        <div class="table-scroll">
        <table><thead><tr><th>Asesor</th><th>Desde</th><th>Hasta</th><th>Meses activo</th><th>Ejecutado</th><th>% Participación</th></tr></thead><tbody id="tblResumenVentasEjecucion"></tbody></table>
        </div>
      </div>
    </section>'''
assert old_resumen_close in final_html, "No se encontro el cierre de Resumen"
final_html = final_html.replace(old_resumen_close, new_resumen_close)

# --- 14c-JS: (corregido 27-ago x2, a pedido de Luis) sin meta ni % ejecucion -- ordenado de
# mayor a menor por lo ejecutado, con % de participacion sobre el total del equipo y una fila
# de Total al final. +Desde/Hasta (rango de meses activo) se mantiene.
old_rowsven = '''  const rowsVen = advisorsFull.map(a=>{
    const r = ventasRankByName[a.name];
    if (!r || !r.meta_acumulada_5m) return null;
    const pct = r.meta_acumulada_5m>0 ? (r.total_acumulado/r.meta_acumulada_5m*100) : null;
    return {name:a.name, meses:a.meses_activos||r.meses_activos, real:r.total_acumulado, meta:r.meta_acumulada_5m, pct};
  }).filter(Boolean).sort((a,b)=>(b.pct||0)-(a.pct||0));
  const tblVenEj = document.getElementById('tblVentasEjecucionAsesor');
  if (tblVenEj) tblVenEj.innerHTML = rowsVen.map(r=>{
    const cls = r.pct!=null? statusClass(r.pct):'na';
    return `<tr><td>${r.name}</td><td>${r.meses}</td><td>${fmt(r.real)}</td><td>${fmt(r.meta)}</td><td><span class="badge ${cls||'ok'}">${r.pct!=null?r.pct.toFixed(0)+'%':'—'}</span></td></tr>`;
  }).join('');'''
new_rowsven = '''  const gesLblVen = DATA.gestiones.month_labels || {};
  const rowsVen = advisorsFull.map(a=>{
    const r = ventasRankByName[a.name];
    const mesesN = a.meses_activos || (r ? r.meses_activos : 0) || 0;
    if (!mesesN) return null;
    const real = r ? (r.total_acumulado||0) : 0;
    const mesesArr = (a.active_months||[]).slice().sort();
    const desde = mesesArr.length? (gesLblVen[mesesArr[0]] || mesesArr[0]) : '—';
    const hasta = mesesArr.length? (gesLblVen[mesesArr[mesesArr.length-1]] || mesesArr[mesesArr.length-1]) : '—';
    return {name:a.name, mesesN, desde, hasta, real};
  }).filter(Boolean).sort((a,b)=>b.real-a.real);
  const totalVenEj = rowsVen.reduce((s,r)=>s+r.real,0);
  const tblVenEj = document.getElementById('tblResumenVentasEjecucion');
  if (tblVenEj) tblVenEj.innerHTML = rowsVen.map(r=>{
    const part = totalVenEj>0 ? (r.real/totalVenEj*100) : 0;
    return `<tr><td>${r.name}</td><td>${r.desde}</td><td>${r.hasta}</td><td>${r.mesesN}</td><td>${fmt(r.real)}</td><td>${part.toFixed(1)}%</td></tr>`;
  }).join('') + `<tr style="font-weight:700;background:#f4f6f5;"><td colspan="4">Total</td><td>${fmt(totalVenEj)}</td><td>100%</td></tr>`;'''
assert old_rowsven in final_html, "No se encontro el bloque rowsVen a corregir"
final_html = final_html.replace(old_rowsven, new_rowsven)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 14 aplicado: tabla Ejecucion vs. meta Ventas vuelve a Resumen, +Desde/Hasta, meta recalculada con la tasa mensual REAL de cada asesor x sus meses activos actuales (ya no se mide igual a 2 meses que a 6).")

# ---------- 15. Resumen: "Ejecucion de Gestion (equipo)" -- cantidad en vez de % (27-ago-2026, a pedido de Luis) ----------
# Luis: en vez de ver el % de ejecucion de cada frente (Promocion/Mantenimiento/Ventas/Medios
# de contacto), prefiere ver la CANTIDAD real de gestiones de cada uno, + un total que sume
# gestion + medios de contacto.
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()
old_resumen_gestion_cant = '''document.getElementById('resumenGestionEquipo').innerHTML = contract.categories.map(cat=>{
  const inds = cat.indicators.filter(i=>!i.pending);
  let real=0, expected=0;
  inds.forEach(i=>{ real += i.real; expected += i.meta_6m*contract.elapsed_fraction; });
  const pct = expected>0 ? Math.min(real/expected,1.5)*100 : 0;
  return `<div class="kpi"><div class="kv">${pct.toFixed(0)}%</div><div class="kl">${cat.name} — % ejecución</div></div>`;
}).join('');'''
new_resumen_gestion_cant = '''const gestionCatCant = contract.categories.map(cat=>{
  // Se excluyen indicadores en $ (ej. "Ventas efectivas totales ($)") -- son monto vendido, no
  // cantidad de gestiones, y sumarlos junto a conteos de actividades daria un numero sin sentido.
  const inds = cat.indicators.filter(i=>!i.pending && !/\\(\\$\\)/.test(i.name));
  const real = inds.reduce((s,i)=>s+i.real,0);
  return {name:cat.name, real};
});
const gestionCatTotal = gestionCatCant.reduce((s,c)=>s+c.real,0);
document.getElementById('resumenGestionEquipo').innerHTML =
  gestionCatCant.map(c=>`<div class="kpi"><div class="kv">${fmtN(c.real)}</div><div class="kl">${c.name} — cantidad</div></div>`).join('') +
  `<div class="kpi acc"><div class="kv">${fmtN(gestionCatTotal)}</div><div class="kl">Total (gestión + medios de contacto)</div></div>`;'''
assert old_resumen_gestion_cant in final_html, "No se encontro el bloque de resumenGestionEquipo"
final_html = final_html.replace(old_resumen_gestion_cant, new_resumen_gestion_cant)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 15 aplicado: Resumen -- 'Ejecucion de Gestion (equipo)' ahora muestra cantidad real por frente (Promocion/Mantenimiento/Ventas/Medios de contacto) + Total combinado, en vez de %.")


# ---------- 16. Resumen: mes en curso + 4 cuadros mes-a-mes + tabla asesores +2 cols (31-ago-2026, a pedido de Luis, imagenes hoja_resumen) ----------
# Ver docx "cambios hoja de resumen" (31-ago-2026): tarjeta espejo de resumenKpis pero del mes en
# curso; quitar "Ejecucion de Ventas/Empresas/Gestion (equipo)"; agregar 4 cuadros categoria x mes
# (Gestion integral, Medios de contacto, Ventas por servicio, Empresas por tamano) con linea de
# tendencia cada uno; tabla de Ejecucion de Ventas (por asesor) +2 columnas (mes en curso + total).
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_html_16 = 'grid" id="resumenKpis"></div>\n      <div class="grid2">\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Ventas ejecutadas — tendencia marzo a la fecha</span></div>\n          <div class="chart-box"><canvas id="chResumenTendencia"></canvas></div>\n        </div>\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Empresas por estado de contacto</span></div>\n          <div class="chart-box"><canvas id="chResumenEmpresas"></canvas></div>\n        </div>\n      </div>\n\n      <div class="grid2">\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Ejecución de Ventas (equipo)</span></div>\n          <div class="kpi-grid" id="resumenVentasEquipo"></div>\n        </div>\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Ejecución de Empresas (equipo)</span></div>\n          <div class="kpi-grid" id="resumenEmpresasEquipo"></div>\n        </div>\n      </div>\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Ejecución de Gestión (equipo) — por frente de contrato</span></div>\n        <div class="kpi-grid" id="resumenGestionEquipo"></div>\n      </div>\n\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Ejecución de Ventas (por asesor)</span></div>\n        <div class="section-desc">Ordenado de mayor a menor por lo ejecutado. % Participación = qué parte del total vendido por el equipo aporta cada asesor.</div>\n        <div class="table-scroll">\n        <table><thead><tr><th>Asesor</th><th>Desde</th><th>Hasta</th><th>Meses activo</th><th>Ejecutado</th><th>% Participación</th></tr></thead><tbody id="tblResumenVentasEjecucion"></tbody></table>'
new_html_16 = 'grid" id="resumenKpis"></div>\n      <div class="section-desc" style="margin-top:10px;">Mismos indicadores, pero del mes en curso.</div>\n      <div class="kpi-grid" id="resumenKpisMes"></div>\n      <div class="grid2">\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Ventas ejecutadas — tendencia marzo a la fecha</span></div>\n          <div class="chart-box"><canvas id="chResumenTendencia"></canvas></div>\n        </div>\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Empresas por estado de contacto</span></div>\n          <div class="chart-box"><canvas id="chResumenEmpresas"></canvas></div>\n        </div>\n      </div>\n\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Gestión integral — por mes</span></div>\n        <div class="table-scroll"><table id="tblResumenGestionMes"></table></div>\n        <div class="chart-box" style="height:220px;margin-top:12px;"><canvas id="chResumenGestionMesTendencia"></canvas></div>\n      </div>\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Medios de contacto — por mes</span></div>\n        <div class="table-scroll"><table id="tblResumenMediosMes"></table></div>\n        <div class="chart-box" style="height:220px;margin-top:12px;"><canvas id="chResumenMediosMesTendencia"></canvas></div>\n      </div>\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Ventas por servicio — cantidad por mes</span></div>\n        <div class="table-scroll"><table id="tblResumenVentasServMes"></table></div>\n        <div class="chart-box" style="height:220px;margin-top:12px;"><canvas id="chResumenVentasServMesTendencia"></canvas></div>\n      </div>\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Empresas atendidas por tamaño — por mes</span></div>\n        <div class="table-scroll"><table id="tblResumenEmpresasTamMes"></table></div>\n        <div class="chart-box" style="height:220px;margin-top:12px;"><canvas id="chResumenEmpresasTamMesTendencia"></canvas></div>\n      </div>\n\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Ejecución de Ventas (por asesor)</span></div>\n        <div class="section-desc">Ordenado de mayor a menor por el Total (acumulado + mes en curso). % Participación = qué parte del acumulado vendido por el equipo aporta cada asesor.</div>\n        <div class="table-scroll">\n        <table><thead><tr><th>Asesor</th><th>Desde</th><th>Hasta</th><th>Meses activo</th><th>Ejecutado</th><th>% Participación</th><th>Ejecución mes en curso</th><th>Total</th></tr></thead><tbody id="tblResumenVentasEjecucion"></tbody></table>'
assert old_html_16 in final_html, "Paso 16: no se encontro el bloque HTML de Resumen a reemplazar"
assert final_html.count(old_html_16)==1
final_html = final_html.replace(old_html_16, new_html_16)

old_js_16a = '// ---- Ejecución a nivel de EQUIPO (reemplaza las 2 tablas por-asesor que salieron de Resumen) ----\nconst mesActualTendEq = ventasD.tendencia[ventasD.tendencia.length-1];\nconst pctMesEquipo = mesActualTendEq.meta>0 ? (mesActualTendEq.ventas/mesActualTendEq.meta*100) : 0;\ndocument.getElementById(\'resumenVentasEquipo\').innerHTML = `\n  <div class="kpi"><div class="kv">${fmtM(mesActualTendEq.ventas)}</div><div class="kl">Ejecutado ${mesActualTendEq.mes}${mesActualTendEq.parcial?\' (parcial)\':\'\'}</div></div>\n  <div class="kpi"><div class="kv">${pctMesEquipo.toFixed(0)}%</div><div class="kl">% Ejecución del mes</div></div>\n  <div class="kpi acc"><div class="kv">${fmtM(acumEjecutadoEq)}</div><div class="kl">Ejecutado acumulado</div></div>\n  <div class="kpi"><div class="kv">${pctAcumEquipo.toFixed(0)}%</div><div class="kl">% Ejecución acumulada</div></div>\n`;\n\nconst totalEmpEquipo = DATA.empresas_agg.total;\nconst contactadasEquipo = DATA.empresas_agg.per_counts[\'Contactada - contrato actual\']||0;\nconst noContactadasEquipo = DATA.empresas_agg.per_counts[\'No contactada\']||0;\ndocument.getElementById(\'resumenEmpresasEquipo\').innerHTML = `\n  <div class="kpi"><div class="kv">${fmtN(totalEmpEquipo)}</div><div class="kl">Empresas en el padrón</div></div>\n  <div class="kpi acc"><div class="kv">${totalEmpEquipo?((contactadasEquipo/totalEmpEquipo)*100).toFixed(0):0}%</div><div class="kl">% Contactadas (contrato actual)</div></div>\n  <div class="kpi bad"><div class="kv">${fmtN(noContactadasEquipo)}</div><div class="kl">Sin contactar</div></div>\n`;\n\nconst gestionCatCant = contract.categories.map(cat=>{\n  // Se excluyen indicadores en $ (ej. "Ventas efectivas totales ($)") -- son monto vendido, no\n  // cantidad de gestiones, y sumarlos junto a conteos de actividades daria un numero sin sentido.\n  const inds = cat.indicators.filter(i=>!i.pending && !/\\(\\$\\)/.test(i.name));\n  const real = inds.reduce((s,i)=>s+i.real,0);\n  return {name:cat.name, real};\n});\nconst gestionCatTotal = gestionCatCant.reduce((s,c)=>s+c.real,0);\ndocument.getElementById(\'resumenGestionEquipo\').innerHTML =\n  gestionCatCant.map(c=>`<div class="kpi"><div class="kv">${fmtN(c.real)}</div><div class="kl">${c.name} — cantidad</div></div>`).join(\'\') +\n  `<div class="kpi acc"><div class="kv">${fmtN(gestionCatTotal)}</div><div class="kl">Total (gestión + medios de contacto)</div></div>`;\n'
new_js_16a = '// ---- Mes en curso (31-ago-2026, a pedido de Luis): tarjetas espejo de resumenKpis + 4 cuadros mes-a-mes ----\nconst ymActual = ventasD.meses_order[ventasD.meses_order.length-1];\nconst mesLabelActual = ventasD.mes_labels[ymActual] || ymActual;\nconst rawGesAllTop = DATA.gestiones.raw_gestiones || [];\nconst rawGesMesTop = rawGesAllTop.filter(r=>(r.fecha||\'\').slice(0,7)===ymActual);\nconst mesActualTendEq = ventasD.tendencia[ventasD.tendencia.length-1];\nconst pctMesEquipo = mesActualTendEq.meta>0 ? (mesActualTendEq.ventas/mesActualTendEq.meta*100) : 0;\n\nfunction countTagPeriodo(rows, tag){\n  return rows.filter(r=>(r.gestion||\'\').split(\'/\').some(p=>p.trim()===tag)).length;\n}\nconst MEDIO_MAP_TOP = {\'Llamada\':\'Llamadas\',\'WhatsApp\':\'WhatsApp\',\'Correo electrónico\':\'Correos\',\'Visita presencial\':\'Visitas presenciales\',\'Reunión virtual\':\'Reunión virtual\'};\n// % ejecución del mes (Gestión): solo Promoción + Mantenimiento + Medios de contacto -- son los\n// unicos frentes con fuente mensual real (raw_gestiones/medio). Ventas (Cotizaciones, Ordenes de\n// compra, etc.) es conteo de negociaciones de Bitrix sin desglose mensual disponible en DATA, asi\n// que se deja fuera de este promedio (su $ si tiene mes en curso propio, en la tarjeta de al lado).\nconst NOMBRE_TAG_GESTION = {\n  \'Actualización de base de datos\': \'Actualización de datos\',\n  \'Visita por primera vez\': \'Empresa contactada por primera vez\',\n  \'Presentación de portafolio\': \'Presentación de Portafolio\',\n};\nlet sumaPctGesMes = 0, nIndGesMes = 0;\ncontract.categories.forEach(cat=>{\n  if (cat.name===\'Ventas\') return;\n  cat.indicators.forEach(ind=>{\n    if (ind.pending) return;\n    const metaMes = (ind.meta_6m||0)/6;\n    if (!(metaMes>0)) return;\n    let realMes;\n    if (cat.name===\'Medios de contacto\') realMes = rawGesMesTop.filter(r=>MEDIO_MAP_TOP[r.medio]===ind.name).length;\n    else realMes = countTagPeriodo(rawGesMesTop, NOMBRE_TAG_GESTION[ind.name] || ind.name);\n    sumaPctGesMes += Math.min(realMes/metaMes, 1.5);\n    nIndGesMes++;\n  });\n});\nconst pctGestionMes = nIndGesMes ? (sumaPctGesMes/nIndGesMes*100) : 0;\nconst nitEmpMesSet = new Set(rawGesMesTop.map(r=>r.nit).filter(Boolean));\nconst nitEmpPrimeraVezMesSet = new Set(rawGesMesTop.filter(r=>(r.gestion||\'\').split(\'/\').some(p=>p.trim()===\'Empresa contactada por primera vez\')).map(r=>r.nit).filter(Boolean));\n\ndocument.getElementById(\'resumenKpisMes\').innerHTML = `\n  <div class="kpi"><div class="kv">${pctGestionMes.toFixed(0)}%</div><div class="kl">Ejecución del mes (Gestión)</div></div>\n  <div class="kpi acc"><div class="kv">${fmtM(mesActualTendEq.ventas)}</div><div class="kl">Ventas ejecutadas (${mesLabelActual})</div></div>\n  <div class="kpi"><div class="kv">${fmtM(mesActualTendEq.meta)}</div><div class="kl">Meta del mes (${pctMesEquipo.toFixed(0)}% ejecutado)</div></div>\n  <div class="kpi"><div class="kv">${fmtN(nitEmpMesSet.size)}</div><div class="kl">Empresas atendidas este mes</div></div>\n  <div class="kpi"><div class="kv">${fmtN(nitEmpPrimeraVezMesSet.size)}</div><div class="kl">Contactadas por primera vez este mes</div></div>\n`;\n\n// ---- Helper generico: tabla categoria x mes con totales + grafico de linea ----\nfunction renderMatrizMes(elId, chartId, rows, months, monthLabels, dataFn, chartLabel, color){\n  const totalPorMes = {}; months.forEach(m=>totalPorMes[m]=0);\n  let totalGeneral = 0;\n  const bodyRows = rows.map(r=>{\n    let rowTotal = 0;\n    const tds = months.map(m=>{\n      const v = dataFn(r.key, m) || 0;\n      totalPorMes[m] += v; rowTotal += v;\n      return `<td>${v.toLocaleString(\'es-CO\')}</td>`;\n    }).join(\'\');\n    totalGeneral += rowTotal;\n    return `<tr><td>${r.label}</td>${tds}<td style="font-weight:700;">${rowTotal.toLocaleString(\'es-CO\')}</td></tr>`;\n  }).join(\'\');\n  const totalRow = `<tr style="font-weight:700;background:#f4f6f5;"><td>Total</td>${months.map(m=>`<td>${totalPorMes[m].toLocaleString(\'es-CO\')}</td>`).join(\'\')}<td>${totalGeneral.toLocaleString(\'es-CO\')}</td></tr>`;\n  const thead = `<thead><tr><th>Categoría</th>${months.map(m=>`<th>${monthLabels[m]||m}</th>`).join(\'\')}<th>Total</th></tr></thead>`;\n  const elTable = document.getElementById(elId);\n  if (elTable) elTable.innerHTML = thead + \'<tbody>\' + bodyRows + totalRow + \'</tbody>\';\n  const elChart = document.getElementById(chartId);\n  if (elChart) new Chart(elChart, {\n    type:\'line\',\n    data:{ labels: months.map(m=>monthLabels[m]||m), datasets:[{ label: chartLabel, data: months.map(m=>totalPorMes[m]||0), borderColor:color, backgroundColor:color+\'33\', fill:true, tension:0.3, pointRadius:3 }] },\n    options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}}\n  });\n  return totalPorMes;\n}\n\n// 1) Gestión integral por mes (mismas 10 categorías del informe mensual)\nconst CATS_GESTION_ROWS = [\n  [\'Asesorías generales\',\'Asesorías generales\'],\n  [\'Presentación de Portafolio\',\'Presentación de portafolio\'],\n  [\'Empresa contactada por primera vez\',\'Empresa contactada por primera vez\'],\n  [\'Actualización de datos\',\'Actualización de datos\'],\n  [\'Actividades de mantenimiento\',\'Actividades de mantenimiento\'],\n  [\'Gestión fallida\',\'Gestión fallida\'],\n  [\'Seguimiento ventas\',\'Seguimiento de ventas\'],\n  [\'Acompañamiento servicio postventa\',\'Acompañamiento postventa\'],\n  [\'Feria de servicios\',\'Feria de servicios\'],\n  [\'Empresa ilocalizable\',\'Empresa ilocalizable\'],\n].map(([key,label])=>({key,label}));\nfunction countTagMonth(rows, tag, ym){\n  return rows.filter(r=>(r.fecha||\'\').slice(0,7)===ym && (r.gestion||\'\').split(\'/\').some(p=>p.trim()===tag)).length;\n}\nrenderMatrizMes(\'tblResumenGestionMes\',\'chResumenGestionMesTendencia\', CATS_GESTION_ROWS, ventasD.meses_order, ventasD.mes_labels,\n  (key,ym)=>countTagMonth(rawGesAllTop, key, ym), \'Gestiones\', \'#00685E\');\n\n// 2) Medios de contacto por mes\nconst MEDIOS_ROWS = [\n  [\'Llamada\',\'Llamadas\'],[\'WhatsApp\',\'WhatsApp\'],[\'Correo electrónico\',\'Correos\'],\n  [\'Visita presencial\',\'Visitas presenciales\'],[\'Reunión virtual\',\'Reunión virtual\'],\n].map(([key,label])=>({key,label}));\nrenderMatrizMes(\'tblResumenMediosMes\',\'chResumenMediosMesTendencia\', MEDIOS_ROWS, ventasD.meses_order, ventasD.mes_labels,\n  (key,ym)=>rawGesAllTop.filter(r=>(r.fecha||\'\').slice(0,7)===ym && r.medio===key).length, \'Medios de contacto\', \'#FF6900\');\n\n// 3) Ventas por servicio por mes (catalogo oficial, cantidad de ventas) -- se llena mas abajo,\n// despues de que el Paso de Ventas calcule ventasD.transacciones[].servicio_oficial.\nwindow.__renderVentasServicioMes = function(){\n  const catalogo = Object.keys(IMPUESTO_OFICIAL).map(k=>({key:k,label:k}));\n  renderMatrizMes(\'tblResumenVentasServMes\',\'chResumenVentasServMesTendencia\', catalogo, ventasD.meses_order, ventasD.mes_labels,\n    (key,ym)=>ventasD.transacciones.filter(t=>t.ym===ym && t.servicio_oficial===key).length, \'Ventas\', \'#1F2A44\');\n};\n\n// 4) Empresas atendidas por tamaño por mes\nconst empTamByNitTop = {};\n(DATA.empresas_full||[]).forEach(e=>{ empTamByNitTop[e.nit] = e.tam || \'Sin dato\'; });\nconst TAM_ROWS = [[\'Grande\',\'Grande\'],[\'Mediana\',\'Mediana\'],[\'Pequeña\',\'Pequeña\'],[\'Micro\',\'Micro\']].map(([key,label])=>({key,label}));\nrenderMatrizMes(\'tblResumenEmpresasTamMes\',\'chResumenEmpresasTamMesTendencia\', TAM_ROWS, ventasD.meses_order, ventasD.mes_labels,\n  (tam,ym)=>{\n    const nits = new Set();\n    rawGesAllTop.forEach(r=>{ if((r.fecha||\'\').slice(0,7)===ym && r.nit && empTamByNitTop[r.nit]===tam) nits.add(r.nit); });\n    return nits.size;\n  }, \'Empresas atendidas\', \'#8850A0\');\n\n'
assert old_js_16a in final_html, "Paso 16: no se encontro el bloque JS de tarjetas equipo (resumenVentasEquipo/resumenGestionEquipo)"
assert final_html.count(old_js_16a)==1
final_html = final_html.replace(old_js_16a, new_js_16a)

old_js_16b = 'const gesLblVen = DATA.gestiones.month_labels || {};\n  const rowsVen = advisorsFull.map(a=>{\n    const r = ventasRankByName[a.name];\n    const mesesN = a.meses_activos || (r ? r.meses_activos : 0) || 0;\n    if (!mesesN) return null;\n    const real = r ? (r.total_acumulado||0) : 0;\n    const mesesArr = (a.active_months||[]).slice().sort();\n    const desde = mesesArr.length? (gesLblVen[mesesArr[0]] || mesesArr[0]) : \'—\';\n    const hasta = mesesArr.length? (gesLblVen[mesesArr[mesesArr.length-1]] || mesesArr[mesesArr.length-1]) : \'—\';\n    return {name:a.name, mesesN, desde, hasta, real};\n  }).filter(Boolean).sort((a,b)=>b.real-a.real);\n  const totalVenEj = rowsVen.reduce((s,r)=>s+r.real,0);\n  const tblVenEj = document.getElementById(\'tblResumenVentasEjecucion\');\n  if (tblVenEj) tblVenEj.innerHTML = rowsVen.map(r=>{\n    const part = totalVenEj>0 ? (r.real/totalVenEj*100) : 0;\n    return `<tr><td>${r.name}</td><td>${r.desde}</td><td>${r.hasta}</td><td>${r.mesesN}</td><td>${fmt(r.real)}</td><td>${part.toFixed(1)}%</td></tr>`;\n  }).join(\'\') + `<tr style="font-weight:700;background:#f4f6f5;"><td colspan="4">Total</td><td>${fmt(totalVenEj)}</td><td>100%</td></tr>`;\n\n  '
new_js_16b = 'const gesLblVen = DATA.gestiones.month_labels || {};\n  const mesActualVenByAsesor = {};\n  ventasD.transacciones.forEach(t=>{\n    if (t.ym===ymActual) mesActualVenByAsesor[t.asesor] = (mesActualVenByAsesor[t.asesor]||0) + t.valor;\n  });\n  const rowsVen = advisorsFull.map(a=>{\n    const r = ventasRankByName[a.name];\n    const mesesN = a.meses_activos || (r ? r.meses_activos : 0) || 0;\n    const mesActualVal = mesActualVenByAsesor[a.name] || 0;\n    if (!mesesN && !mesActualVal) return null;\n    const real = r ? (r.total_acumulado||0) : 0;\n    const mesesArr = (a.active_months||[]).slice().sort();\n    const desde = mesesArr.length? (gesLblVen[mesesArr[0]] || mesesArr[0]) : \'—\';\n    const hasta = mesesArr.length? (gesLblVen[mesesArr[mesesArr.length-1]] || mesesArr[mesesArr.length-1]) : \'—\';\n    return {name:a.name, mesesN, desde, hasta, real, mesActualVal};\n  }).filter(Boolean);\n  // Asesores con venta este mes que no aparecen en advisorsFull (p.ej. salieron sin que Luis lo\n  // haya confirmado aun) igual deben ver su valor de mes en curso -- no depende del roster.\n  const yaIncluidosVen = new Set(rowsVen.map(r=>r.name));\n  Object.keys(mesActualVenByAsesor).forEach(name=>{\n    if (yaIncluidosVen.has(name)) return;\n    rowsVen.push({name, mesesN:0, desde:\'—\', hasta:\'—\', real:0, mesActualVal: mesActualVenByAsesor[name]});\n  });\n  rowsVen.forEach(r=>{ r.total = r.real + r.mesActualVal; });\n  rowsVen.sort((a,b)=>b.total-a.total);\n  const totalVenEj = rowsVen.reduce((s,r)=>s+r.real,0);\n  const totalMesVenEj = rowsVen.reduce((s,r)=>s+r.mesActualVal,0);\n  const totalGralVenEj = rowsVen.reduce((s,r)=>s+r.total,0);\n  const tblVenEj = document.getElementById(\'tblResumenVentasEjecucion\');\n  if (tblVenEj) tblVenEj.innerHTML = rowsVen.map(r=>{\n    const part = totalVenEj>0 ? (r.real/totalVenEj*100) : 0;\n    return `<tr><td>${r.name}</td><td>${r.desde}</td><td>${r.hasta}</td><td>${r.mesesN}</td><td>${fmt(r.real)}</td><td>${part.toFixed(1)}%</td><td>${fmt(r.mesActualVal)}</td><td style="font-weight:700;">${fmt(r.total)}</td></tr>`;\n  }).join(\'\') + `<tr style="font-weight:700;background:#f4f6f5;"><td colspan="4">Total</td><td>${fmt(totalVenEj)}</td><td>100%</td><td>${fmt(totalMesVenEj)}</td><td>${fmt(totalGralVenEj)}</td></tr>`;\n\n\n'
assert old_js_16b in final_html, "Paso 16: no se encontro el IIFE de tblResumenVentasEjecucion"
assert final_html.count(old_js_16b)==1
final_html = final_html.replace(old_js_16b, new_js_16b)

anchor_16 = "populateSelect('fVenServicio', [...new Set(ventasD.transacciones.map(r=>r.servicio_oficial))].sort());"
assert anchor_16 in final_html and final_html.count(anchor_16)==1, "Paso 16: no se encontro el anchor de servicio_oficial"
final_html = final_html.replace(anchor_16, anchor_16 + "\n if (window.__renderVentasServicioMes) window.__renderVentasServicioMes();")

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 16 aplicado: Resumen -- tarjetas mes en curso, 4 cuadros mes-a-mes (gestion/medios/ventas-servicio/empresas-tamano) con tendencia, y tabla de ventas por asesor +2 columnas (mes en curso + total).")


# ---------- 17. Gestión (Equipo): merge tarjetas, reordenar zonas, tarjeta Indicadores, quitar boton Excel (31-ago-2026, a pedido de Luis, "Hoja de gestion.docx") ----------
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_merge_17 = '''    <div class="kpi ok"><div class="kv">${bestInd? (bestInd[1].pctSum/bestInd[1].pctN*100).toFixed(0)+'%':'—'}</div><div class="kl">Mejor indicador: ${bestInd?bestInd[0]:'—'}</div></div>
    <div class="kpi"><div class="kv">${indRanked.length?indRanked[0][0]:'—'}</div><div class="kl">Actividad más realizada (${indRanked.length?fmtN(indRanked[0][1].real):0})</div></div>
    <div class="kpi"><div class="kv">${fmtN(cotizTotal.real)}/${fmtN(cotizTotal.meta)}</div><div class="kl">Cotizaciones (equipo)</div></div>
    <div class="kpi"><div class="kv">${fmtN(ocTotal.real)}/${fmtN(ocTotal.meta)}</div><div class="kl">Órdenes de compra (equipo)</div></div>'''
new_merge_17 = '''    <div class="kpi ok"><div class="kv">${bestInd?bestInd[0]:'—'}</div><div class="kl">Mejor indicador (${bestInd?(bestInd[1].pctSum/bestInd[1].pctN*100).toFixed(0)+'%':'—'}) · más realizada (${indRanked.length?fmtN(indRanked[0][1].real):0})</div></div>
    <div class="kpi"><div class="kv">${fmtN(cotizTotal.real)}/${fmtN(cotizTotal.meta)}</div><div class="kl">Cotizaciones (equipo)</div></div>
    <div class="kpi"><div class="kv">${fmtN(ocTotal.real)}/${fmtN(ocTotal.meta)}</div><div class="kl">Órdenes de compra (equipo)</div></div>'''
assert old_merge_17 in final_html, "Paso 17: no se encontro el bloque de tarjetas Mejor indicador/Actividad mas realizada"
final_html = final_html.replace(old_merge_17, new_merge_17)

old_zona_17 = '''  document.getElementById('gestionZonaCards').innerHTML = Object.entries(zonaGestion).map(([z,inds])=>{
    const pcts = Object.values(inds).filter(v=>v.meta>0).map(v=>Math.min(v.real/v.meta,1.5));
    const pctAvg = pcts.length? (pcts.reduce((s,p)=>s+p,0)/pcts.length*100) : 0;
    const nAse = zonaAdvisorSet[z] ? zonaAdvisorSet[z].size : 0;
    return `<div class="zona-card"><h3>${z}</h3><div class="zona-row">Asesores <b>${nAse}</b></div><div class="zona-row">Cumplimiento promedio <b>${pctAvg.toFixed(0)}%</b></div></div>`;
  }).join('');'''
new_zona_17 = '''  const ZONA_ORDEN = ['Santa Marta','Call Center','IFT','Ciénaga','Fundación'];
  document.getElementById('gestionZonaCards').innerHTML = Object.entries(zonaGestion)
    .sort((a,b)=>ZONA_ORDEN.indexOf(a[0])-ZONA_ORDEN.indexOf(b[0]))
    .map(([z,inds])=>{
    const pcts = Object.values(inds).filter(v=>v.meta>0).map(v=>Math.min(v.real/v.meta,1.5));
    const pctAvg = pcts.length? (pcts.reduce((s,p)=>s+p,0)/pcts.length*100) : 0;
    const nAse = zonaAdvisorSet[z] ? zonaAdvisorSet[z].size : 0;
    return `<div class="zona-card"><h3>${z}</h3><div class="zona-row">Asesores <b>${nAse}</b></div><div class="zona-row">Cumplimiento promedio <b>${pctAvg.toFixed(0)}%</b></div></div>`;
  }).join('');'''
assert old_zona_17 in final_html, "Paso 17: no se encontro el bloque de gestionZonaCards"
final_html = final_html.replace(old_zona_17, new_zona_17)

old_card_17 = '''        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Medios de contacto — real vs. meta (equipo, acumulado del contrato)</span></div>
          <div class="kpi-grid" id="gestionMediosMetas"></div>
        </div>'''
new_card_17 = '''        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Indicadores de gestión — real vs. meta (equipo, acumulado del contrato)</span></div>
          <div class="kpi-grid" id="gestionIndicadoresMetas"></div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Medios de contacto — real vs. meta (equipo, acumulado del contrato)</span></div>
          <div class="kpi-grid" id="gestionMediosMetas"></div>
        </div>'''
assert old_card_17 in final_html, "Paso 17: no se encontro la tarjeta HTML de Medios de contacto"
final_html = final_html.replace(old_card_17, new_card_17)

old_js_medios_17 = '''document.getElementById('gestionMediosMetas').innerHTML'''
new_js_medios_17 = '''document.getElementById('gestionIndicadoresMetas').innerHTML = contract.categories
  .filter(c=>c.name==='Promoción' || c.name==='Mantenimiento')
  .flatMap(c=>c.indicators).filter(i=>!i.pending).map(i=>{
    const expected = i.meta_6m*contract.elapsed_fraction;
    const pct = expected>0 ? Math.min(i.real/expected,1.5)*100 : 0;
    const cls = statusClass(pct);
    return `<div class="kpi ${cls}"><div class="kv">${pct.toFixed(0)}%</div><div class="kl">${i.name}</div><div class="ks">${fmtN(i.real)} / ${fmtN(i.meta_6m)} meta contrato</div></div>`;
  }).join('');

document.getElementById('gestionMediosMetas').innerHTML'''
assert final_html.count(old_js_medios_17)==1, "Paso 17: no se encontro (unica vez) el fill de gestionMediosMetas"
final_html = final_html.replace(old_js_medios_17, new_js_medios_17)

old_btn_17 = '''            <span><span class="dot"></span>Detalle de gestiones (filtrable)</span>
            <button class="filter-clear" id="btnExportGes">⬇ Exportar a Excel</button>
          </div>'''
new_btn_17 = '''            <span><span class="dot"></span>Detalle de gestiones (filtrable)</span>
          </div>'''
assert old_btn_17 in final_html, "Paso 17: no se encontro el boton btnExportGes"
final_html = final_html.replace(old_btn_17, new_btn_17)

old_listener_17 = '''document.getElementById('btnExportGes').addEventListener('click', ()=>{
  // sin filtro de asesor/otros -> exporta TODO; si hay filtros activos, exporta solo lo filtrado (incluye asesor si fue seleccionado explícitamente vía el select de arriba)
  const q = document.getElementById('fGesBuscar').value.trim();
  const tipo = document.getElementById('fGesTipo').value, medio = document.getElementById('fGesMedio').value;
  const desde = document.getElementById('fGesDesde').value, hasta = document.getElementById('fGesHasta').value;
  const anyFilter = q || tipo || medio || desde || hasta;
  let rows = DATA.gestiones.raw_gestiones || [];
  if (!anyFilter){
    // sin filtro alguno: exporta información general completa, sin filtrar por asesor
  } else {
    rows = getGestionesFiltered(true);
  }
  exportToExcel(rows.map(r=>({Fecha:r.fecha, Asesor:r.asesor, Comentario:r.comentario||'', Gestión:r.gestion||'', Medio:r.medio||'', Empresa:r.empresa||'', NIT:r.nit||''})), 'Gestiones_CAJAMAG');
});

// (Contrato Cajamag eliminado de Operativo el 26-ago-2026, a pedido de Luis)'''
new_listener_17 = '''// (Botón "Exportar a Excel" de Gestión eliminado de Operativo el 31-ago-2026, a pedido de Luis; se mantiene en Gerencial)

// (Contrato Cajamag eliminado de Operativo el 26-ago-2026, a pedido de Luis)'''
assert old_listener_17 in final_html, "Paso 17: no se encontro el listener de btnExportGes"
final_html = final_html.replace(old_listener_17, new_listener_17)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 17 aplicado: Gestion (Equipo) -- tarjetas 'Mejor indicador'+'Actividad mas realizada' fusionadas, zonas reordenadas (Santa Marta/Call Center/IFT/Cienaga/Fundacion), nueva tarjeta 'Indicadores de gestion' (Promocion+Mantenimiento), y boton 'Exportar a Excel' de Detalle de gestiones eliminado (solo Operativo).")

# ---------- 18. Empresas: quitar tarjetas sesgadas por asesor activo, +3 tarjetas a nivel equipo,
# numero+% visible en donas, reordenar/fusionar zona (31-ago-2026, a pedido de Luis, "Hoja de empresas.docx") ----------
# Luis: "Empresas gestionadas (contrato)"/"Faltantes por gestionar" sesgaban a los asesores activos
# ("a mi me sirve mas ver a CER en esta parte como un equipo"). Se reemplazan por 3 tarjetas nuevas
# a nivel EQUIPO (mismas 3 categorias de 'per' ya usadas arriba, sin filtrar por asesor activo):
#   - Faltan re-contactar (ya contactadas contrato anterior) = contAnterior
#   - Faltan contactar en general este contrato (con o sin historia anterior) = contAnterior + noCont
#   - Oportunidades de contacto por primera vez = noCont
# PENDIENTE (no incluido aqui, requiere el feed de contrato-pasado que Luis pidio dejar para el final):
#   1) "cuantas contactadas del contrato anterior YA re-contactamos este contrato" -- el campo 'per'
#      se sobrescribe a 'Contactada - contrato actual' en cuanto hay una gestion nueva, asi que se
#      pierde el dato de si esa empresa TAMBIEN tenia historia de contrato anterior.
#   2) "cuantas gestionadas del contrato anterior ya no se pueden gestionar porque no pertenecen a
#      nuestra base de datos" -- requiere diff contra el padron de empresas del contrato anterior.
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_html_18 = '''        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Estado de contacto</span></div>
          <div class="chart-box sm"><canvas id="chEmpresasPer"></canvas></div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Estado de afiliación</span></div>
          <div class="chart-box sm"><canvas id="chEmpresasEst"></canvas></div>
        </div>
      </div>
      <div class="grid3">
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Por asesor (top 10)</span></div>
          <div class="chart-box sm"><canvas id="chEmpresasAsesor"></canvas></div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Por zona/equipo</span></div>
          <div class="chart-box sm"><canvas id="chEmpresasZona"></canvas></div>
        </div>'''
new_html_18 = '''        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Estado de contacto</span></div>
          <div class="chart-box sm"><canvas id="chEmpresasPer"></canvas></div>
          <div id="chEmpresasPerLegend" style="margin-top:8px;"></div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Estado de afiliación</span></div>
          <div class="chart-box sm"><canvas id="chEmpresasEst"></canvas></div>
          <div id="chEmpresasEstLegend" style="margin-top:8px;"></div>
        </div>
      </div>
      <div class="grid3">
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Por asesor (top 10)</span></div>
          <div class="chart-box sm"><canvas id="chEmpresasAsesor"></canvas></div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Por zona/equipo</span></div>
          <div class="chart-box sm"><canvas id="chEmpresasZona"></canvas></div>
        </div>'''
assert old_html_18 in final_html, "Paso 18: no se encontro el bloque HTML de Estado de contacto/afiliacion/zona"
final_html = final_html.replace(old_html_18, new_html_18)

old_kpis_18 = '''  // ---- Asignadas/gestionadas/faltantes (26-ago-2026, a pedido de Luis: se movió aquí desde Gestión) ----
  // Sigue el mismo filtro de Asesor que ya existe arriba: si hay uno elegido, muestra sus 3 números;
  // si está en "Todos", suma el equipo activo completo.
  const aseSelEmp = document.getElementById('fEmpAse').value;
  let empAsigK, empGestK, empFaltK, empLblK;
  if (aseSelEmp){
    const aEmp = advisorsFull.find(x=>x.name===aseSelEmp);
    empAsigK = aEmp ? (aEmp.empresas_asignadas||0) : 0;
    empGestK = aEmp ? (aEmp.empresas_gestionadas_contrato||0) : 0;
    empFaltK = aEmp ? (aEmp.empresas_faltantes_contrato||0) : 0;
    empLblK = aseSelEmp;
  } else {
    empAsigK = activeAdvisors.reduce((s,x)=>s+(x.empresas_asignadas||0),0);
    empGestK = activeAdvisors.reduce((s,x)=>s+(x.empresas_gestionadas_contrato||0),0);
    empFaltK = activeAdvisors.reduce((s,x)=>s+(x.empresas_faltantes_contrato||0),0);
    empLblK = 'equipo';
  }
  document.getElementById('empresasKpis').insertAdjacentHTML('beforeend', `
    <div class="kpi"><div class="kv">${fmtN(empAsigK)}</div><div class="kl">Empresas asignadas — ${empLblK}</div></div>
    <div class="kpi acc"><div class="kv">${fmtN(empGestK)}</div><div class="kl">Empresas gestionadas (contrato)</div></div>
    <div class="kpi bad"><div class="kv">${fmtN(empFaltK)}</div><div class="kl">Faltantes por gestionar</div></div>
  `);'''
new_kpis_18 = '''  // ---- Reencuadre a nivel EQUIPO, sin sesgo por asesor activo/inactivo (31-ago-2026, a pedido de
  // Luis: "Empresas gestionadas (contrato)"/"Faltantes por gestionar" sesgaban a los asesores activos
  // y no le sirven -- "a mi me sirve mas ver a CER en esta parte como un equipo"). Se calculan
  // directo sobre el filtro de empresas (mismas 3 categorias de 'per' de arriba), no por asesor.
  const faltaReContactar = contAnterior; // ya contactamos en el contrato anterior, aun no en este
  const faltaContactarGeneral = contAnterior + noCont; // no tocadas EN ESTE contrato (con o sin historia anterior)
  const oportunidadPrimeraVez = noCont; // nunca contactadas, en ningun contrato
  document.getElementById('empresasKpis').insertAdjacentHTML('beforeend', `
    <div class="kpi warn"><div class="kv">${fmtN(faltaReContactar)}</div><div class="kl">Faltan re-contactar (ya contactadas contrato anterior, ${pct(faltaReContactar)}%)</div></div>
    <div class="kpi bad"><div class="kv">${fmtN(faltaContactarGeneral)}</div><div class="kl">Faltan contactar en general este contrato (${pct(faltaContactarGeneral)}%)</div></div>
    <div class="kpi bad"><div class="kv">${fmtN(oportunidadPrimeraVez)}</div><div class="kl">Oportunidades de contacto por primera vez (${pct(oportunidadPrimeraVez)}%)</div></div>
  `);'''
assert old_kpis_18 in final_html, "Paso 18: no se encontro el bloque JS de Asignadas/gestionadas/faltantes"
final_html = final_html.replace(old_kpis_18, new_kpis_18)

old_donas_18 = '''  // Estado de contacto
  const perCounts = countBy(rows, 'per');
  const perLabels = Object.keys(perCounts);
  const perData = Object.values(perCounts);
  const perPalette = ['#00685E','#FF6900','#D2CE9E','#B8B8B8'];
  if (!chEmpPer){
    chEmpPer = new Chart(document.getElementById('chEmpresasPer'),{
      type:'doughnut', data:{labels:perLabels, datasets:[{data:perData, backgroundColor:perPalette}]},
      options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}}
    });
  } else { chEmpPer.data.labels=perLabels; chEmpPer.data.datasets[0].data=perData; chEmpPer.update(); }

  // Estado de afiliación
  const estCounts = countBy(rows, 'est');
  const estLabels = Object.keys(estCounts);
  const estData = Object.values(estCounts);
  const estColors = estLabels.map(l=>EMP_COLORS.est[l]||'#999');
  if (!chEmpEst){
    chEmpEst = new Chart(document.getElementById('chEmpresasEst'),{
      type:'doughnut', data:{labels:estLabels, datasets:[{data:estData, backgroundColor:estColors}]},
      options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}}
    });
  } else { chEmpEst.data.labels=estLabels; chEmpEst.data.datasets[0].data=estData; chEmpEst.update(); }'''
new_donas_18 = '''  // Estado de contacto
  const perCounts = countBy(rows, 'per');
  const perLabels = Object.keys(perCounts);
  const perData = Object.values(perCounts);
  const perPalette = ['#00685E','#FF6900','#D2CE9E','#B8B8B8'];
  if (!chEmpPer){
    chEmpPer = new Chart(document.getElementById('chEmpresasPer'),{
      type:'doughnut', data:{labels:perLabels, datasets:[{data:perData, backgroundColor:perPalette}]},
      options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}}
    });
  } else { chEmpPer.data.labels=perLabels; chEmpPer.data.datasets[0].data=perData; chEmpPer.update(); }
  // 31-ago-2026, a pedido de Luis: numero + % visibles siempre (no solo al pasar el mouse).
  document.getElementById('chEmpresasPerLegend').innerHTML = perLabels.map((l,i)=>
    `<div class="zona-row"><span>${l}</span><b>${fmtN(perData[i])} (${pct(perData[i])}%)</b></div>`
  ).join('');

  // Estado de afiliación
  const estCounts = countBy(rows, 'est');
  const estLabels = Object.keys(estCounts);
  const estData = Object.values(estCounts);
  const estColors = estLabels.map(l=>EMP_COLORS.est[l]||'#999');
  if (!chEmpEst){
    chEmpEst = new Chart(document.getElementById('chEmpresasEst'),{
      type:'doughnut', data:{labels:estLabels, datasets:[{data:estData, backgroundColor:estColors}]},
      options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}}
    });
  } else { chEmpEst.data.labels=estLabels; chEmpEst.data.datasets[0].data=estData; chEmpEst.update(); }
  document.getElementById('chEmpresasEstLegend').innerHTML = estLabels.map((l,i)=>
    `<div class="zona-row"><span>${l}</span><b>${fmtN(estData[i])} (${pct(estData[i])}%)</b></div>`
  ).join('');'''
assert old_donas_18 in final_html, "Paso 18: no se encontro el bloque JS de las donas Estado de contacto/afiliacion"
final_html = final_html.replace(old_donas_18, new_donas_18)

old_zona_18 = '''  // Por zona/equipo
  const zonaCounts = countBy(rows,'eq');
  const zonaLabels = Object.keys(zonaCounts);
  const zonaData = Object.values(zonaCounts);
  if (!chEmpZona){
    chEmpZona = new Chart(document.getElementById('chEmpresasZona'),{
      type:'bar', data:{labels:zonaLabels, datasets:[{label:'Empresas', data:zonaData, backgroundColor:'#00685Eaa'}]},
      options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}}
    });
  } else { chEmpZona.data.labels=zonaLabels; chEmpZona.data.datasets[0].data=zonaData; chEmpZona.update(); }'''
new_zona_18 = '''  // Por zona/equipo (31-ago-2026, a pedido de Luis: orden logico Santa Marta/Contact Center/IFT/
  // Cienaga/Fundacion, y "Sin equipo asignado" se suma dentro de Santa Marta).
  const zonaCounts = countBy(rows,'eq');
  if (zonaCounts['Sin equipo asignado']){
    zonaCounts['Santa Marta'] = (zonaCounts['Santa Marta']||0) + zonaCounts['Sin equipo asignado'];
    delete zonaCounts['Sin equipo asignado'];
  }
  const ZONA_EMP_ORDEN = ['Santa Marta','Contact Center','IFT','Cienaga','Fundacion'];
  const zonaLabels = Object.keys(zonaCounts).sort((a,b)=>ZONA_EMP_ORDEN.indexOf(a)-ZONA_EMP_ORDEN.indexOf(b));
  const zonaData = zonaLabels.map(l=>zonaCounts[l]);
  if (!chEmpZona){
    chEmpZona = new Chart(document.getElementById('chEmpresasZona'),{
      type:'bar', data:{labels:zonaLabels, datasets:[{label:'Empresas', data:zonaData, backgroundColor:'#00685Eaa'}]},
      options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}}
    });
  } else { chEmpZona.data.labels=zonaLabels; chEmpZona.data.datasets[0].data=zonaData; chEmpZona.update(); }'''
assert old_zona_18 in final_html, "Paso 18: no se encontro el bloque JS de Por zona/equipo"
final_html = final_html.replace(old_zona_18, new_zona_18)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 18 aplicado: Empresas -- tarjetas 'Empresas gestionadas (contrato)'/'Faltantes por gestionar' (sesgadas a asesores activos) reemplazadas por 3 tarjetas a nivel equipo; numero+%% visible en donas Estado de contacto/afiliacion; 'Por zona/equipo' reordenada (Santa Marta/Contact Center/IFT/Cienaga/Fundacion) con 'Sin equipo asignado' sumado a Santa Marta.")

# --- Paso 19. Empresas: unificar tarjetas KPI duplicadas (31-ago-2026, a pedido de Luis: "me di
# cuenta que hay 2 tarjetas que dicen lo mismo y otras dos mas miralo y unificalos"). Las 3 tarjetas
# nuevas de Paso 18 repetian, en 2 de los 3 casos, los mismos numeros que las tarjetas de la fila de
# arriba (contAnterior y noCont). Se relabelan esas tarjetas de arriba para absorber el concepto
# duplicado y se deja solo la unica metrica que no estaba en ningun lado ("falta contactar en
# general este contrato").
old_row1_19 = '''  document.getElementById('empresasKpis').innerHTML = `
    <div class="kpi"><div class="kv">${fmtN(total)}</div><div class="kl">Empresas (según filtro)</div></div>
    <div class="kpi acc"><div class="kv">${fmtN(contActual)}</div><div class="kl">Contactadas contrato actual (${pct(contActual)}%)</div></div>
    <div class="kpi warn"><div class="kv">${fmtN(contAnterior)}</div><div class="kl">Solo contrato anterior (${pct(contAnterior)}%)</div></div>
    <div class="kpi bad"><div class="kv">${fmtN(noCont)}</div><div class="kl">No contactadas (${pct(noCont)}%)</div></div>
  `;'''
new_row1_19 = '''  document.getElementById('empresasKpis').innerHTML = `
    <div class="kpi"><div class="kv">${fmtN(total)}</div><div class="kl">Empresas (según filtro)</div></div>
    <div class="kpi acc"><div class="kv">${fmtN(contActual)}</div><div class="kl">Contactadas contrato actual (${pct(contActual)}%)</div></div>
    <div class="kpi warn"><div class="kv">${fmtN(contAnterior)}</div><div class="kl">Solo contrato anterior — faltan re-contactar (${pct(contAnterior)}%)</div></div>
    <div class="kpi bad"><div class="kv">${fmtN(noCont)}</div><div class="kl">No contactadas — oportunidad de primera vez (${pct(noCont)}%)</div></div>
  `;'''
assert old_row1_19 in final_html, "Paso 19: no se encontro la fila 1 de tarjetas de Empresas"
final_html = final_html.replace(old_row1_19, new_row1_19)

old_row2_19 = '''  const faltaReContactar = contAnterior; // ya contactamos en el contrato anterior, aun no en este
  const faltaContactarGeneral = contAnterior + noCont; // no tocadas EN ESTE contrato (con o sin historia anterior)
  const oportunidadPrimeraVez = noCont; // nunca contactadas, en ningun contrato
  document.getElementById('empresasKpis').insertAdjacentHTML('beforeend', `
    <div class="kpi warn"><div class="kv">${fmtN(faltaReContactar)}</div><div class="kl">Faltan re-contactar (ya contactadas contrato anterior, ${pct(faltaReContactar)}%)</div></div>
    <div class="kpi bad"><div class="kv">${fmtN(faltaContactarGeneral)}</div><div class="kl">Faltan contactar en general este contrato (${pct(faltaContactarGeneral)}%)</div></div>
    <div class="kpi bad"><div class="kv">${fmtN(oportunidadPrimeraVez)}</div><div class="kl">Oportunidades de contacto por primera vez (${pct(oportunidadPrimeraVez)}%)</div></div>
  `);'''
new_row2_19 = '''  // 31-ago-2026 (2do ajuste, a pedido de Luis): "Faltan re-contactar" y "Oportunidades de contacto
  // por primera vez" repetian exactamente los mismos numeros que "Solo contrato anterior" y "No
  // contactadas" de arriba -- se unifican esas 2 tarjetas duplicadas dentro de las de arriba (ver
  // etiquetas actualizadas) y aqui solo queda la UNICA metrica que no estaba en ningun lado:
  // "falta contactar en general este contrato", que junta ambos grupos (con y sin historia anterior).
  const faltaContactarGeneral = contAnterior + noCont; // no tocadas EN ESTE contrato (con o sin historia anterior)
  document.getElementById('empresasKpis').insertAdjacentHTML('beforeend', `
    <div class="kpi bad"><div class="kv">${fmtN(faltaContactarGeneral)}</div><div class="kl">Faltan contactar en general este contrato, sin contar historia anterior (${pct(faltaContactarGeneral)}%)</div></div>
  `);'''
assert old_row2_19 in final_html, "Paso 19: no se encontro la fila 2 (tarjetas duplicadas) de Empresas"
final_html = final_html.replace(old_row2_19, new_row2_19)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 19 aplicado: Empresas -- unificadas las 2 tarjetas duplicadas ('Faltan re-contactar' y 'Oportunidades de contacto por primera vez') dentro de las tarjetas de arriba (relabel), dejando solo la metrica nueva 'Faltan contactar en general este contrato'.")

# --- Paso 20. Ventas: linea de meta dinamica en "Tendencia mensual (segun filtro)" (1-sep-2026,
# a pedido de Luis: "cuando se filtre bien sea por un asesor o una zona, esta linea llamada meta
# contractual (referencia) se ajuste a la meta del asesor"). Reutiliza la misma tasa mensual real
# de cada asesor ya validada en Resumen (meta_acumulada_5m / meses_activos con que se calculo,
# con 21M/mes de respaldo para asesores sin ranking de ventas aun -- ver Paso 14). Sin filtro de
# asesor/zona, la linea se mantiene igual que antes (meta_contractual_mensual, el numero de equipo).
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_tendmeta_20 = '''  // ---- Tendencia mensual (dentro del filtro) ----
  const tendData = ventasD.meses_order.map(ym=>porMes[ym]||0);
  const tendLabels = ventasD.meses_order.map(ym=>ventasD.mes_labels[ym]);
  const tendMeta = ventasD.meses_order.map(()=>ventasD.meta_contractual_mensual);
  if (!chVentasTendencia){
    chVentasTendencia = new Chart(document.getElementById('chVentasTendencia'),{
      type:'bar', data:{ labels: tendLabels,
        datasets:[
          {label:'Ejecutado (filtro)', data: tendData, backgroundColor:'#00685Eaa', borderRadius:5},
          {label:'Meta contractual (referencia)', data: tendMeta, type:'line', borderColor:'#1F2A44', borderDash:[6,4], pointRadius:2, fill:false},
        ]}, options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}, scales:{y:{ticks:{callback:v=>(v/1000000)+'M'}}}}
    });
  } else {
    chVentasTendencia.data.datasets[0].data = tendData;
    chVentasTendencia.update();
  }'''
new_tendmeta_20 = '''  // ---- Tendencia mensual (dentro del filtro) ----
  const tendData = ventasD.meses_order.map(ym=>porMes[ym]||0);
  const tendLabels = ventasD.meses_order.map(ym=>ventasD.mes_labels[ym]);
  function tasaMensualAsesor(a){
    const r = ventasRankByName[a.name];
    if (r && r.meta_acumulada_5m && r.meses_activos) return r.meta_acumulada_5m / r.meses_activos;
    return 21000000;
  }
  const aseSelVen = document.getElementById('fVenAsesor').value;
  const zonaSelVen = document.getElementById('fVenZona').value;
  let metaMensualLinea = ventasD.meta_contractual_mensual;
  if (aseSelVen){
    const aVen = advisorsFull.find(x=>x.name===aseSelVen);
    metaMensualLinea = aVen ? tasaMensualAsesor(aVen) : 0;
  } else if (zonaSelVen){
    metaMensualLinea = activeAdvisors.filter(a=>a.current_profile===zonaSelVen).reduce((s,a)=>s+tasaMensualAsesor(a),0);
  }
  const tendMeta = ventasD.meses_order.map(()=>metaMensualLinea);
  const metaLineLabel = aseSelVen ? `Meta del asesor (${aseSelVen})` : (zonaSelVen ? `Meta de la zona (${zonaSelVen})` : 'Meta contractual (referencia)');
  if (!chVentasTendencia){
    chVentasTendencia = new Chart(document.getElementById('chVentasTendencia'),{
      type:'bar', data:{ labels: tendLabels,
        datasets:[
          {label:'Ejecutado (filtro)', data: tendData, backgroundColor:'#00685Eaa', borderRadius:5},
          {label:metaLineLabel, data: tendMeta, type:'line', borderColor:'#1F2A44', borderDash:[6,4], pointRadius:2, fill:false},
        ]}, options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}, scales:{y:{ticks:{callback:v=>(v/1000000)+'M'}}}}
    });
  } else {
    chVentasTendencia.data.datasets[0].data = tendData;
    chVentasTendencia.data.datasets[1].data = tendMeta;
    chVentasTendencia.data.datasets[1].label = metaLineLabel;
    chVentasTendencia.update();
  }'''
assert old_tendmeta_20 in final_html, "Paso 20: no se encontro el bloque JS de Tendencia mensual (Ventas)"
final_html = final_html.replace(old_tendmeta_20, new_tendmeta_20)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 20 aplicado: Ventas -- linea de meta en 'Tendencia mensual' ahora dinamica segun el filtro (meta del asesor si se filtra por asesor, suma de metas de la zona si se filtra por zona, meta contractual del equipo si no hay filtro).")

# ---------- 21. Resumen: tabla "Ejecucion de Ventas (por asesor)" -- quitar % Participacion,
# ordenar por Ejecucion mes en curso, renombrar Ejecutado (2-sep-2026, a pedido de Luis:
# "quita la variable de participacion organiza siempre por la variable ejecucion mes en curso
# de mayor a menor y donde dice ejecutado cambiale el nombre a ejecutado meses anteriores") ----------
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_desc_21 = '''<div class="section-desc">Ordenado de mayor a menor por el Total (acumulado + mes en curso). % Participación = qué parte del acumulado vendido por el equipo aporta cada asesor.</div>
        <div class="table-scroll">
        <table><thead><tr><th>Asesor</th><th>Desde</th><th>Hasta</th><th>Meses activo</th><th>Ejecutado</th><th>% Participación</th><th>Ejecución mes en curso</th><th>Total</th></tr></thead><tbody id="tblResumenVentasEjecucion"></tbody></table>'''
new_desc_21 = '''<div class="section-desc">Ordenado de mayor a menor por la Ejecución mes en curso.</div>
        <div class="table-scroll">
        <table><thead><tr><th>Asesor</th><th>Desde</th><th>Hasta</th><th>Meses activo</th><th>Ejecutado meses anteriores</th><th>Ejecución mes en curso</th><th>Total</th></tr></thead><tbody id="tblResumenVentasEjecucion"></tbody></table>'''
assert old_desc_21 in final_html, "Paso 21: no se encontro el bloque HTML de la tabla Ejecucion de Ventas"
final_html = final_html.replace(old_desc_21, new_desc_21)

old_sort_21 = '''rowsVen.sort((a,b)=>b.total-a.total);'''
new_sort_21 = '''rowsVen.sort((a,b)=>b.mesActualVal-a.mesActualVal);'''
assert old_sort_21 in final_html, "Paso 21: no se encontro el sort de rowsVen"
final_html = final_html.replace(old_sort_21, new_sort_21)

old_render_21 = '''if (tblVenEj) tblVenEj.innerHTML = rowsVen.map(r=>{
    const part = totalVenEj>0 ? (r.real/totalVenEj*100) : 0;
    return `<tr><td>${r.name}</td><td>${r.desde}</td><td>${r.hasta}</td><td>${r.mesesN}</td><td>${fmt(r.real)}</td><td>${part.toFixed(1)}%</td><td>${fmt(r.mesActualVal)}</td><td style="font-weight:700;">${fmt(r.total)}</td></tr>`;
  }).join('') + `<tr style="font-weight:700;background:#f4f6f5;"><td colspan="4">Total</td><td>${fmt(totalVenEj)}</td><td>100%</td><td>${fmt(totalMesVenEj)}</td><td>${fmt(totalGralVenEj)}</td></tr>`;'''
new_render_21 = '''if (tblVenEj) tblVenEj.innerHTML = rowsVen.map(r=>{
    return `<tr><td>${r.name}</td><td>${r.desde}</td><td>${r.hasta}</td><td>${r.mesesN}</td><td>${fmt(r.real)}</td><td>${fmt(r.mesActualVal)}</td><td style="font-weight:700;">${fmt(r.total)}</td></tr>`;
  }).join('') + `<tr style="font-weight:700;background:#f4f6f5;"><td colspan="4">Total</td><td>${fmt(totalVenEj)}</td><td>${fmt(totalMesVenEj)}</td><td>${fmt(totalGralVenEj)}</td></tr>`;'''
assert old_render_21 in final_html, "Paso 21: no se encontro el render de filas de rowsVen"
final_html = final_html.replace(old_render_21, new_render_21)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 21 aplicado: Resumen -- tabla 'Ejecucion de Ventas (por asesor)' sin columna % Participacion, ordenada por Ejecucion mes en curso (de mayor a menor), 'Ejecutado' renombrado a 'Ejecutado meses anteriores'.")

# ---------- 22. Empresas: filtro por fecha "contactadas hasta" (2-sep-2026, a pedido de Luis:
# "en esta hoja falta un filtro por fecha para saber hasta que fecha se habian contactado
# cuantas empresas y demas"). Recalcula, para cada empresa, si ya habia sido contactada EN EL
# CONTRATO ACTUAL usando la fecha de su primera gestion registrada (raw_gestiones) comparada
# contra la fecha de corte elegida -- las tarjetas, graficas, tabla y Excel de Empresas ya leen
# todos de getEmpresasFiltered(), asi que remapear 'per' ahi los actualiza a todos a la vez, sin
# tocar cada uno por separado. 'Contactada - solo contrato anterior' e 'Ilocalizable' no dependen
# de esta fecha (son de un contrato o revision distinta) y quedan igual. ----------
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_filters_22 = '''      <div class="filters">
        <div class="filter-group"><label>Buscar</label><input type="text" id="fEmpBuscar" placeholder="Nombre o NIT..."></div>
        <div class="filter-group"><label>Estado de contacto</label><select id="fEmpPer"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Estado</label><select id="fEmpEstado"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Tamaño</label><select id="fEmpTam"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Estado afiliación</label><select id="fEmpEst"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Asesor</label><select id="fEmpAse"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Equipo/Zona</label><select id="fEmpEq"><option value="">Todas</option></select></div>
        <div class="filter-group"><label>Dificultad</label><select id="fEmpDif"><option value="">Todas</option></select></div>
        <button class="filter-clear" id="btnClearEmp">Limpiar</button>
      </div>'''
new_filters_22 = '''      <div class="filters">
        <div class="filter-group"><label>Buscar</label><input type="text" id="fEmpBuscar" placeholder="Nombre o NIT..."></div>
        <div class="filter-group"><label>Estado de contacto</label><select id="fEmpPer"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Estado</label><select id="fEmpEstado"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Tamaño</label><select id="fEmpTam"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Estado afiliación</label><select id="fEmpEst"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Asesor</label><select id="fEmpAse"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Equipo/Zona</label><select id="fEmpEq"><option value="">Todas</option></select></div>
        <div class="filter-group"><label>Dificultad</label><select id="fEmpDif"><option value="">Todas</option></select></div>
        <div class="filter-group"><label>Contactadas hasta (contrato actual)</label><input type="date" id="fEmpHastaFecha"></div>
        <button class="filter-clear" id="btnClearEmp">Limpiar</button>
      </div>
      <div class="section-desc" id="empFechaCorteNota" style="display:none;"></div>'''
assert old_filters_22 in final_html, "Paso 22: no se encontro el panel de filtros de Empresas (post-Paso 9)"
final_html = final_html.replace(old_filters_22, new_filters_22)

old_top_22 = '''function estadoUnificado(r){
  if (r.iloc) return 'Ilocalizable';
  if (r.per === 'No contactada') return 'Primer contacto';
  return 'Ya se encontró';
}
const ESTADO_ORDER = ['Ya se encontró','Primer contacto','Ilocalizable'];'''
new_top_22 = '''function estadoUnificado(r){
  if (r.iloc) return 'Ilocalizable';
  if (r.per === 'No contactada') return 'Primer contacto';
  return 'Ya se encontró';
}
const ESTADO_ORDER = ['Ya se encontró','Primer contacto','Ilocalizable'];

// Fecha de corte (2-sep-2026, a pedido de Luis): primera gestion registrada por NIT, EN EL
// CONTRATO ACTUAL (raw_gestiones solo tiene datos desde marzo-2026 en adelante).
const primerContactoPorNit = {};
(DATA.gestiones.raw_gestiones||[]).forEach(r=>{
  if (!r.nit || !r.fecha) return;
  if (!primerContactoPorNit[r.nit] || r.fecha < primerContactoPorNit[r.nit]) primerContactoPorNit[r.nit] = r.fecha;
});
function perAsOfFecha(r, hastaFecha){
  // Solo se recalcula la dimension "contrato actual" (Contactada/No contactada); "Contactada -
  // solo contrato anterior" e Ilocalizable no dependen de la fecha de corte elegida.
  if (r.per !== 'Contactada - contrato actual' && r.per !== 'No contactada') return r.per;
  const pc = primerContactoPorNit[r.nit];
  return (pc && pc <= hastaFecha) ? 'Contactada - contrato actual' : 'No contactada';
}'''
assert old_top_22 in final_html, "Paso 22: no se encontro estadoUnificado/ESTADO_ORDER"
final_html = final_html.replace(old_top_22, new_top_22)

old_gef_22 = '''function getEmpresasFiltered(){
  const q = document.getElementById('fEmpBuscar').value.trim().toLowerCase();
  const per = document.getElementById('fEmpPer').value;
  const estado = document.getElementById('fEmpEstado').value;
  const tam = document.getElementById('fEmpTam').value;
  const est = document.getElementById('fEmpEst').value;
  const ase = document.getElementById('fEmpAse').value;
  const eq = document.getElementById('fEmpEq').value;
  const dif = document.getElementById('fEmpDif').value;
  let rows = empFull;
  if (q) rows = rows.filter(r => (r.nom||'').toLowerCase().includes(q) || (r.nit||'').includes(q));
  if (per) rows = rows.filter(r=>r.per===per);
  if (estado) rows = rows.filter(r=>estadoUnificado(r)===estado);
  if (tam) rows = rows.filter(r=>r.tam===tam);
  if (est) rows = rows.filter(r=>r.est===est);
  if (ase) rows = rows.filter(r=>r.ase===ase);
  if (eq) rows = rows.filter(r=>r.eq===eq);
  if (dif) rows = rows.filter(r=>r.dif===dif);
  return rows;
}'''
new_gef_22 = '''function getEmpresasFiltered(){
  const q = document.getElementById('fEmpBuscar').value.trim().toLowerCase();
  const per = document.getElementById('fEmpPer').value;
  const estado = document.getElementById('fEmpEstado').value;
  const tam = document.getElementById('fEmpTam').value;
  const est = document.getElementById('fEmpEst').value;
  const ase = document.getElementById('fEmpAse').value;
  const eq = document.getElementById('fEmpEq').value;
  const dif = document.getElementById('fEmpDif').value;
  const hastaFecha = document.getElementById('fEmpHastaFecha').value;
  let rows = empFull;
  if (hastaFecha) rows = rows.map(r=>({...r, per: perAsOfFecha(r, hastaFecha)}));
  if (q) rows = rows.filter(r => (r.nom||'').toLowerCase().includes(q) || (r.nit||'').includes(q));
  if (per) rows = rows.filter(r=>r.per===per);
  if (estado) rows = rows.filter(r=>estadoUnificado(r)===estado);
  if (tam) rows = rows.filter(r=>r.tam===tam);
  if (est) rows = rows.filter(r=>r.est===est);
  if (ase) rows = rows.filter(r=>r.ase===ase);
  if (eq) rows = rows.filter(r=>r.eq===eq);
  if (dif) rows = rows.filter(r=>r.dif===dif);
  return rows;
}'''
assert old_gef_22 in final_html, "Paso 22: no se encontro getEmpresasFiltered (post-Paso 9e)"
final_html = final_html.replace(old_gef_22, new_gef_22)

old_listeners_22 = '''['fEmpBuscar'].forEach(id=>document.getElementById(id).addEventListener('input', renderEmpresasAll));
['fEmpPer','fEmpEstado','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif'].forEach(id=>document.getElementById(id).addEventListener('change', renderEmpresasAll));
document.getElementById('btnClearEmp').addEventListener('click',()=>{
  ['fEmpBuscar','fEmpPer','fEmpEstado','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif'].forEach(id=>document.getElementById(id).value='');
  renderEmpresasAll();
});'''
new_listeners_22 = '''function actualizarNotaFechaCorte(){
  const el = document.getElementById('empFechaCorteNota');
  const v = document.getElementById('fEmpHastaFecha').value;
  if (!el) return;
  if (v){ el.style.display='block'; el.textContent = `Mostrando el estado de contacto (contrato actual) tal como estaba el ${v} — no el estado de hoy.`; }
  else { el.style.display='none'; el.textContent=''; }
}
['fEmpBuscar'].forEach(id=>document.getElementById(id).addEventListener('input', renderEmpresasAll));
['fEmpPer','fEmpEstado','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif'].forEach(id=>document.getElementById(id).addEventListener('change', renderEmpresasAll));
document.getElementById('fEmpHastaFecha').addEventListener('change', ()=>{ actualizarNotaFechaCorte(); renderEmpresasAll(); });
document.getElementById('btnClearEmp').addEventListener('click',()=>{
  ['fEmpBuscar','fEmpPer','fEmpEstado','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif','fEmpHastaFecha'].forEach(id=>document.getElementById(id).value='');
  actualizarNotaFechaCorte();
  renderEmpresasAll();
});'''
assert old_listeners_22 in final_html, "Paso 22: no se encontro el bloque de listeners de Empresas (post-Paso 9g)"
final_html = final_html.replace(old_listeners_22, new_listeners_22)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 22 aplicado: Empresas -- nuevo filtro de fecha 'Contactadas hasta (contrato actual)'; tarjetas/graficas/tabla/Excel recalculan el estado de contacto tal como estaba en esa fecha (usando la primera gestion registrada por NIT).")

# ---------- 23. Resumen: "Ventas por servicio" -- cambia de tabla+linea mes-a-mes a barras
# horizontales rankeadas por valor (2-sep-2026, a pedido de Luis: "el cuadro y la grafica de
# ventas por servicio no me gusto mejor cambiala con la grafica de barra de ventas por servicio
# que esta en el tablero tv"). Mismo estilo visual que Tablero_TV_Asesores_CER.html
# (renderVentasPorServicio): nombre + barra proporcional al maximo + valor $ + cantidad + % del
# total, top 8 servicios + "Otros", pero sobre el CONTRATO COMPLETO a la fecha (no un mes suelto,
# ya que esta tarjeta vive en Resumen junto a las demas vistas de "todo el contrato"). ----------
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_card_23 = '''      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ventas por servicio — cantidad por mes</span></div>
        <div class="table-scroll"><table id="tblResumenVentasServMes"></table></div>
        <div class="chart-box" style="height:220px;margin-top:12px;"><canvas id="chResumenVentasServMesTendencia"></canvas></div>
      </div>'''
new_card_23 = '''      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ventas por servicio (contrato completo a la fecha)</span></div>
        <style>
          .svc-row{display:grid;grid-template-columns:200px 1fr 170px;align-items:center;gap:10px;margin:7px 0;}
          .svc-name{font-size:.85rem;color:var(--text-muted, #555);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
          .svc-bar-wrap{background:#eef1f0;border-radius:5px;height:16px;overflow:hidden;}
          .svc-bar{height:100%;border-radius:5px;}
          .svc-vals{display:flex;flex-direction:column;font-size:.8rem;text-align:right;line-height:1.25;}
          .svc-money{font-weight:700;}
          .svc-sub{color:var(--text-muted, #777);}
        </style>
        <div id="resumenVentasServicioBars"></div>
      </div>'''
assert old_card_23 in final_html, "Paso 23: no se encontro la tarjeta 'Ventas por servicio -- cantidad por mes'"
final_html = final_html.replace(old_card_23, new_card_23)

old_fn_23 = '''window.__renderVentasServicioMes = function(){
  const catalogo = Object.keys(IMPUESTO_OFICIAL).map(k=>({key:k,label:k}));
  renderMatrizMes(\'tblResumenVentasServMes\',\'chResumenVentasServMesTendencia\', catalogo, ventasD.meses_order, ventasD.mes_labels,
    (key,ym)=>ventasD.transacciones.filter(t=>t.ym===ym && t.servicio_oficial===key).length, \'Ventas\', \'#1F2A44\');
};'''
new_fn_23 = '''const SVC_COLORS_RESUMEN = [\'#5b8def\',\'#3ecf8e\',\'#f5a524\',\'#ee6c6c\',\'#a78bfa\',\'#22c1c3\',\'#f472b6\',\'#c084fc\',\'#94a3b8\'];
window.__renderVentasServicioMes = function(){
  const porServicio = {};
  ventasD.transacciones.forEach(t=>{
    const k = t.servicio_oficial || \'Sin clasificar\';
    if (!porServicio[k]) porServicio[k] = {servicio:k, valor:0, cantidad:0};
    porServicio[k].valor += (t.valor||0);
    porServicio[k].cantidad += 1;
  });
  let rows = Object.values(porServicio).sort((a,b)=>b.valor-a.valor);
  if (rows.length > 8){
    const top8 = rows.slice(0,8);
    const otros = rows.slice(8).reduce((acc,r)=>{ acc.valor+=r.valor; acc.cantidad+=r.cantidad; return acc; }, {servicio:\'Otros\', valor:0, cantidad:0});
    rows = [...top8, otros];
  }
  const el = document.getElementById(\'resumenVentasServicioBars\');
  if (!el) return;
  if (!rows.length){ el.innerHTML = \'<div style="padding:20px;text-align:center;color:var(--text-muted);">Sin datos de servicio</div>\'; return; }
  const maxVal = Math.max(...rows.map(r=>r.valor), 1);
  const totalVal = rows.reduce((s,r)=>s+r.valor, 0);
  el.innerHTML = rows.map((r,i)=>{
    const pct = Math.max(4, (r.valor/maxVal)*100);
    const share = totalVal ? ((r.valor/totalVal)*100).toFixed(1) : \'0.0\';
    const color = SVC_COLORS_RESUMEN[i % SVC_COLORS_RESUMEN.length];
    return `<div class="svc-row">
      <div class="svc-name">${r.servicio}</div>
      <div class="svc-bar-wrap"><div class="svc-bar" style="width:${pct}%;background:${color}"></div></div>
      <div class="svc-vals"><span class="svc-money">${fmt(r.valor)}</span><span class="svc-sub">${fmtN(r.cantidad)} ventas · ${share}%</span></div>
    </div>`;
  }).join(\'\');
};'''
assert old_fn_23 in final_html, "Paso 23: no se encontro window.__renderVentasServicioMes"
final_html = final_html.replace(old_fn_23, new_fn_23)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 23 aplicado: Resumen -- 'Ventas por servicio' ahora es una grafica de barras horizontales rankeadas por valor (mismo estilo del Tablero TV: top 8 + Otros, con $ y % del total), sobre el contrato completo a la fecha, en vez de la tabla+linea mes-a-mes.")

# ---------- 24. Resumen: linea comparativa 2025 en "Gestion integral" y "Empresas atendidas"
# (2-sep-2026, a pedido de Luis: "en las grafica de resumen de empresa gestion y medios de
# contacto seria muy bueno que me colocaras otra linea comparando al 2025"). Fuente: DECIMO
# INFORME DE AVANCE CONTRATO 2025-252 (informe final, tabla "COMPONENTE" Abril2025-Enero2026,
# la misma fuente ya usada y validada en el informe Word/PDF de ventas 2025 vs 2026). Igual que
# en ese informe: la serie 2025 arranca en Abril (sin punto en Marzo, el contrato anterior no
# tiene un marzo separado -- esas gestiones se fusionaron con abril). "Medios de contacto" NO
# lleva 2025 porque ese contrato no media por canal (llamada/whatsapp/correo/visita/reunion) --
# medía por proposito de la gestion (asesoria, mantenimiento, portafolio, etc.), taxonomia
# distinta que no se puede comparar 1 a 1 sin inventar una equivalencia falsa. ----------
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_helper_24 = '''function renderMatrizMes(elId, chartId, rows, months, monthLabels, dataFn, chartLabel, color){
  const totalPorMes = {}; months.forEach(m=>totalPorMes[m]=0);
  let totalGeneral = 0;
  const bodyRows = rows.map(r=>{
    let rowTotal = 0;
    const tds = months.map(m=>{
      const v = dataFn(r.key, m) || 0;
      totalPorMes[m] += v; rowTotal += v;
      return `<td>${v.toLocaleString(\'es-CO\')}</td>`;
    }).join(\'\');
    totalGeneral += rowTotal;
    return `<tr><td>${r.label}</td>${tds}<td style="font-weight:700;">${rowTotal.toLocaleString(\'es-CO\')}</td></tr>`;
  }).join(\'\');
  const totalRow = `<tr style="font-weight:700;background:#f4f6f5;"><td>Total</td>${months.map(m=>`<td>${totalPorMes[m].toLocaleString(\'es-CO\')}</td>`).join(\'\')}<td>${totalGeneral.toLocaleString(\'es-CO\')}</td></tr>`;
  const thead = `<thead><tr><th>Categoría</th>${months.map(m=>`<th>${monthLabels[m]||m}</th>`).join(\'\')}<th>Total</th></tr></thead>`;
  const elTable = document.getElementById(elId);
  if (elTable) elTable.innerHTML = thead + \'<tbody>\' + bodyRows + totalRow + \'</tbody>\';
  const elChart = document.getElementById(chartId);
  if (elChart) new Chart(elChart, {
    type:\'line\',
    data:{ labels: months.map(m=>monthLabels[m]||m), datasets:[{ label: chartLabel, data: months.map(m=>totalPorMes[m]||0), borderColor:color, backgroundColor:color+\'33\', fill:true, tension:0.3, pointRadius:3 }] },
    options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}}
  });
  return totalPorMes;
}'''
new_helper_24 = '''function renderMatrizMes(elId, chartId, rows, months, monthLabels, dataFn, chartLabel, color, serie2025){
  const totalPorMes = {}; months.forEach(m=>totalPorMes[m]=0);
  let totalGeneral = 0;
  const bodyRows = rows.map(r=>{
    let rowTotal = 0;
    const tds = months.map(m=>{
      const v = dataFn(r.key, m) || 0;
      totalPorMes[m] += v; rowTotal += v;
      return `<td>${v.toLocaleString(\'es-CO\')}</td>`;
    }).join(\'\');
    totalGeneral += rowTotal;
    return `<tr><td>${r.label}</td>${tds}<td style="font-weight:700;">${rowTotal.toLocaleString(\'es-CO\')}</td></tr>`;
  }).join(\'\');
  const totalRow = `<tr style="font-weight:700;background:#f4f6f5;"><td>Total</td>${months.map(m=>`<td>${totalPorMes[m].toLocaleString(\'es-CO\')}</td>`).join(\'\')}<td>${totalGeneral.toLocaleString(\'es-CO\')}</td></tr>`;
  const thead = `<thead><tr><th>Categoría</th>${months.map(m=>`<th>${monthLabels[m]||m}</th>`).join(\'\')}<th>Total</th></tr></thead>`;
  const elTable = document.getElementById(elId);
  if (elTable) elTable.innerHTML = thead + \'<tbody>\' + bodyRows + totalRow + \'</tbody>\';
  const elChart = document.getElementById(chartId);
  if (elChart){
    const datasets = [{ label: chartLabel, data: months.map(m=>totalPorMes[m]||0), borderColor:color, backgroundColor:color+\'33\', fill:true, tension:0.3, pointRadius:3 }];
    if (serie2025) datasets.push({ label: chartLabel + \' 2025 (contrato anterior)\', data: serie2025, borderColor:\'#8a8f98\', backgroundColor:\'transparent\', borderDash:[6,4], fill:false, tension:0.3, pointRadius:3, spanGaps:false });
    new Chart(elChart, {
      type:\'line\',
      data:{ labels: months.map(m=>monthLabels[m]||m), datasets },
      options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display: !!serie2025}}}
    });
  }
  return totalPorMes;
}

// 2025 (contrato anterior 2025-252) -- fuente: DECIMO INFORME DE AVANCE, tabla COMPONENTE
// Abril2025-Enero2026 (empresas gestionadas / cantidad de gestiones), ya validada en el informe
// Word/PDF de ventas 2025 vs 2026. Alineado por mismo mes calendario que ventasD.meses_order
// (Marzo-Agosto); Marzo queda null porque el contrato anterior no tiene un marzo separado.
const GESTIONES_2025_POR_MES = {\'2026-03\':null, \'2026-04\':2462, \'2026-05\':1258, \'2026-06\':650, \'2026-07\':1243, \'2026-08\':1024};
const EMPRESAS_GESTIONADAS_2025_POR_MES = {\'2026-03\':null, \'2026-04\':1106, \'2026-05\':664, \'2026-06\':363, \'2026-07\':511, \'2026-08\':552};'''
assert old_helper_24 in final_html, "Paso 24: no se encontro renderMatrizMes"
final_html = final_html.replace(old_helper_24, new_helper_24)

old_call_gestion_24 = '''renderMatrizMes(\'tblResumenGestionMes\',\'chResumenGestionMesTendencia\', CATS_GESTION_ROWS, ventasD.meses_order, ventasD.mes_labels,
  (key,ym)=>countTagMonth(rawGesAllTop, key, ym), \'Gestiones\', \'#00685E\');'''
new_call_gestion_24 = '''renderMatrizMes(\'tblResumenGestionMes\',\'chResumenGestionMesTendencia\', CATS_GESTION_ROWS, ventasD.meses_order, ventasD.mes_labels,
  (key,ym)=>countTagMonth(rawGesAllTop, key, ym), \'Gestiones\', \'#00685E\', ventasD.meses_order.map(ym=>GESTIONES_2025_POR_MES[ym]));'''
assert old_call_gestion_24 in final_html, "Paso 24: no se encontro la llamada de renderMatrizMes para Gestion integral"
final_html = final_html.replace(old_call_gestion_24, new_call_gestion_24)

old_call_emp_24 = '''renderMatrizMes(\'tblResumenEmpresasTamMes\',\'chResumenEmpresasTamMesTendencia\', TAM_ROWS, ventasD.meses_order, ventasD.mes_labels,
  (tam,ym)=>{
    const nits = new Set();
    rawGesAllTop.forEach(r=>{ if((r.fecha||\'\').slice(0,7)===ym && r.nit && empTamByNitTop[r.nit]===tam) nits.add(r.nit); });
    return nits.size;
  }, \'Empresas atendidas\', \'#8850A0\');'''
new_call_emp_24 = '''renderMatrizMes(\'tblResumenEmpresasTamMes\',\'chResumenEmpresasTamMesTendencia\', TAM_ROWS, ventasD.meses_order, ventasD.mes_labels,
  (tam,ym)=>{
    const nits = new Set();
    rawGesAllTop.forEach(r=>{ if((r.fecha||\'\').slice(0,7)===ym && r.nit && empTamByNitTop[r.nit]===tam) nits.add(r.nit); });
    return nits.size;
  }, \'Empresas atendidas\', \'#8850A0\', ventasD.meses_order.map(ym=>EMPRESAS_GESTIONADAS_2025_POR_MES[ym]));'''
assert old_call_emp_24 in final_html, "Paso 24: no se encontro la llamada de renderMatrizMes para Empresas atendidas"
final_html = final_html.replace(old_call_emp_24, new_call_emp_24)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 24 aplicado: Resumen -- 'Gestion integral' y 'Empresas atendidas por tamaño' ahora muestran una 2da linea punteada gris con el total 2025 (contrato anterior, fuente: informe de avance final), arrancando en Abril igual que el informe de ventas. 'Medios de contacto' se deja sin comparativo 2025 -- ese contrato no medía por canal, no hay una cifra 2025 equivalente y honesta para comparar.")
