"""
multiempresa_ui.py -- 20-nov-2026 (gestion multiempresa de Bitrix).

Inyecta en los dashboards YA construidos (Operativo y Gerencial) una seccion nueva,
"Multiempresa", con: cobertura por asesor (empresas gestionadas), revision de noviembre
(candidatos a duplicado), vista antes/despues y control de calidad. Tambien agrega una nota
discreta con la fecha de corte en Resumen y Gestion.

Es idempotente (si ya esta inyectada no hace nada) y NO cambia ninguna cifra existente.
Solo lectura: no escribe en Bitrix. El estado de revision que marca Luis se guarda en el
navegador (localStorage) y se puede descargar a CSV.
"""
import re

MARCA = 'id="sec-multiempresa"'

CSS = """
<style id="me-css">
.me-note{font-size:11px;color:var(--text-muted,#6b7280);margin:0 0 10px 0;padding:6px 10px;border-left:3px solid var(--naranja,#f26522);background:rgba(242,101,34,.06);border-radius:4px}
.me-tabs{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 14px}
.me-tab{padding:7px 12px;border-radius:8px;border:1px solid var(--border,#e5e7eb);background:#fff;font-size:12px;font-weight:600;cursor:pointer;color:var(--text-muted,#6b7280)}
.me-tab.on{background:var(--naranja-light,#fff1ea);color:var(--naranja,#f26522);border-color:var(--naranja,#f26522)}
.me-card{background:#fff;border:1px solid var(--border,#e5e7eb);border-radius:10px;padding:12px 14px;margin-bottom:10px}
.me-table{width:100%;border-collapse:collapse;font-size:12px}
.me-table th{text-align:left;padding:7px 8px;font-size:11px;color:#fff;white-space:nowrap}
.me-table td{padding:7px 8px;border-bottom:1px solid var(--border,#e5e7eb);vertical-align:top}
.me-table td.n,.me-table th.n{text-align:right;font-variant-numeric:tabular-nums}
.me-wrap{overflow-x:auto}
.me-btn{padding:6px 11px;border-radius:7px;border:1px solid var(--border,#e5e7eb);background:#fff;font-size:12px;cursor:pointer}
.me-pill{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600;background:#eef2f7}
.me-pill.dup{background:#fde8e8;color:#b42318}.me-pill.ok{background:#e6f4ea;color:#1e7e34}.me-pill.pen{background:#fff4d6;color:#8a6100}
.me-card h4{margin:0 0 6px 0;font-size:13px}.me-muted{color:var(--text-muted,#6b7280);font-size:11px}
</style>
"""

SECTION = """
    <section class="section" id="sec-multiempresa">
      <div class="section-title"><h2>🏢 Multiempresa y revisión de visitas</h2></div>
      <div id="me-root"></div>
    </section>
"""

NAV_ITEM = '<div class="navitem" data-section="multiempresa"><span class="ic">🧩</span>Multiempresa</div>'

JS = r"""
<script id="me-js">
(function(){
  var M = (typeof DATA!=='undefined' && DATA.multiempresa) ? DATA.multiempresa : null;
  if(!M || !M.meses) return;
  var meses = Object.keys(M.meses).sort();
  var mes = meses.indexOf('2026-11')>=0 ? '2026-11' : meses[meses.length-1];
  var KEY = 'cajamag_revision_multiempresa_v1';
  var est = {}; try{ est = JSON.parse(localStorage.getItem(KEY)||'{}'); }catch(e){}
  function guardar(){ try{ localStorage.setItem(KEY, JSON.stringify(est)); }catch(e){} }
  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
  function mesNom(ym){ var n=['','enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']; return n[parseInt(ym.slice(5),10)]+' '+ym.slice(0,4); }
  var NOTA = M.nota || '';
  var tab = 'cobertura';
  var ESTADOS = ['Pendiente','Confirmado duplicado','Visitas distintas'];

  // nota discreta en Resumen y Gestion
  ['sec-resumen','sec-gestion'].forEach(function(id){
    var el = document.getElementById(id);
    if(el && !el.querySelector('.me-note')) el.insertAdjacentHTML('afterbegin','<div class="me-note">'+esc(NOTA)+'</div>');
  });

  function datos(){ return M.meses[mes]; }
  function descuento(c){ return est[c.id]==='Confirmado duplicado' ? Math.max(c.negocios-1,0) : 0; }
  function descPorAsesor(){
    var d={}; datos().candidatos.forEach(function(c){ d[c.asesor]=(d[c.asesor]||0)+descuento(c); }); return d;
  }
  function descargar(nombre, filas){
    var csv = filas.map(function(r){ return r.map(function(x){ x=String(x==null?'':x); return '"'+x.replace(/"/g,'""')+'"'; }).join(','); }).join('\n');
    var a=document.createElement('a'); a.href=URL.createObjectURL(new Blob(['﻿'+csv],{type:'text/csv;charset=utf-8'})); a.download=nombre; document.body.appendChild(a); a.click(); a.remove();
  }

  function vCobertura(){
    var pa = datos().por_asesor, nms = Object.keys(pa).sort(function(a,b){return pa[b].empresas_gestionadas-pa[a].empresas_gestionadas;});
    var h = '<div class="me-card"><p class="me-muted" style="margin:0 0 8px">Visita = un negocio. Empresa gestionada = NIT distinto (principal + adicionales). Estos indicadores no tienen meta todavía y no entran en el % global.</p><div class="me-wrap"><table class="me-table"><thead><tr><th>Asesor</th><th class="n">Negocios</th><th class="n">Visitas presenciales</th><th class="n">Empresas gestionadas</th><th class="n">Gestiones por empresa</th><th class="n">Empresas por negocio</th></tr></thead><tbody>';
    nms.forEach(function(n){ var r=pa[n]; h+='<tr><td>'+esc(n)+'</td><td class="n">'+r.negocios+'</td><td class="n">'+r.visitas_presenciales+'</td><td class="n">'+r.empresas_gestionadas+'</td><td class="n">'+r.gestiones_por_empresa+'</td><td class="n">'+r.empresas_por_visita+'</td></tr>'; });
    return h+'</tbody></table></div></div>';
  }

  function vRevision(){
    var cs = datos().candidatos;
    if(!cs.length) return '<div class="me-card">No hay candidatos en este mes.</div>';
    var h = '<div class="me-card"><b>'+cs.length+' candidatos</b> <span class="me-muted">(visita presencial, mismo asesor, fecha y tipo de evento, negocios creados con menos de 30 min entre uno y otro, grupos de 3 o más). Son candidatos, no prueba de duplicado: confírmalos mirando cada negocio en Bitrix. Solo los «Confirmado duplicado» se descuentan, y solo en la vista Antes / después.</span> <button class="me-btn" id="me-csv-rev" style="margin-left:8px">Descargar CSV</button></div>';
    cs.forEach(function(c){
      var e = est[c.id]||'Pendiente', cls = e==='Confirmado duplicado'?'dup':(e==='Visitas distintas'?'ok':'pen');
      h += '<div class="me-card"><h4>'+esc(c.asesor)+' · '+esc(c.fecha)+' · '+c.negocios+' negocios / '+c.empresas_distintas+' empresas distintas <span class="me-pill '+cls+'">'+esc(e)+'</span></h4><div class="me-muted" style="margin-bottom:6px">'+esc(c.tipo_evento||'')+'</div><div class="me-wrap"><table class="me-table"><thead><tr><th>Negocio</th><th>Empresa</th><th>NIT</th><th>Creado</th></tr></thead><tbody>';
      c.items.forEach(function(it){ h+='<tr><td><a href="'+esc(it.url)+'" target="_blank" rel="noopener">#'+esc(it.deal_id)+'</a></td><td>'+esc(it.empresa)+'</td><td>'+esc(it.nit)+'</td><td>'+esc(it.creado)+'</td></tr>'; });
      h += '</tbody></table></div><div style="margin-top:8px"><select class="me-sel" data-id="'+esc(c.id)+'">'+ESTADOS.map(function(x){return '<option'+(x===e?' selected':'')+'>'+x+'</option>';}).join('')+'</select></div></div>';
    });
    return h;
  }

  function vAntes(){
    var pa = datos().por_asesor, d = descPorAsesor(), nms = Object.keys(pa).sort();
    var h = '<div class="me-card"><p class="me-muted" style="margin:0 0 8px">Simulación: no cambia las visitas ni los porcentajes oficiales del dashboard. Descuenta solo los candidatos marcados como «Confirmado duplicado» (cada grupo cuenta como 1 visita).</p><div class="me-wrap"><table class="me-table"><thead><tr><th>Asesor</th><th class="n">Visitas presenciales</th><th class="n">Descuento confirmado</th><th class="n">Visitas ajustadas</th><th class="n">Meta</th><th class="n">% antes</th><th class="n">% después</th></tr></thead><tbody>';
    nms.forEach(function(n){ var r=pa[n], dd=d[n]||0, adj=r.visitas_presenciales-dd, m=r.meta_visitas_presenciales;
      h+='<tr><td>'+esc(n)+'</td><td class="n">'+r.visitas_presenciales+'</td><td class="n">'+dd+'</td><td class="n">'+adj+'</td><td class="n">'+(m==null?'—':m)+'</td><td class="n">'+(m?Math.round(r.visitas_presenciales/m*1000)/10+'%':'—')+'</td><td class="n">'+(m?Math.round(adj/m*1000)/10+'%':'—')+'</td></tr>'; });
    return h+'</tbody></table></div></div>';
  }

  var filtroRegla = '';
  function vCalidad(){
    var cal = datos().calidad, res = datos().resumen_calidad||{}, reglas = Object.keys(res).sort();
    var h = '<div class="me-card"><b>Control de calidad</b> <span class="me-muted">(negocios desde el '+esc(M.corte)+'). Se recalcula cada hora.</span><div style="margin-top:8px">';
    if(!reglas.length) h += '<span class="me-pill ok">Sin alertas</span>';
    reglas.forEach(function(r){ var info = r.indexOf('Sin grupo conocido')===0; h+='<span class="me-pill '+(filtroRegla===r?'dup':(info?'':'pen'))+'" data-regla="'+esc(r)+'" style="cursor:pointer;margin:0 6px 6px 0">'+esc(r)+': '+res[r]+'</span>'; });
    h += ' <button class="me-btn" id="me-csv-cal">Descargar CSV</button></div></div>';
    var f = cal.filter(function(x){ return !filtroRegla || x.regla===filtroRegla; });
    if(f.length) { h += '<div class="me-card"><div class="me-wrap"><table class="me-table"><thead><tr><th>Regla</th><th>Negocio</th><th>Asesor</th><th>Fecha</th><th>Empresa</th><th>Detalle</th></tr></thead><tbody>';
      f.forEach(function(x){ h+='<tr><td>'+esc(x.regla)+'</td><td><a href="'+esc(x.url)+'" target="_blank" rel="noopener">#'+esc(x.deal_id)+'</a></td><td>'+esc(x.asesor)+'</td><td>'+esc(x.fecha)+'</td><td>'+esc(x.empresa)+'</td><td>'+esc(x.detalle)+'</td></tr>'; });
      h += '</tbody></table></div></div>'; }
    return h;
  }

  function render(){
    var root = document.getElementById('me-root'); if(!root) return;
    var tabs = [['cobertura','Cobertura'],['revision','Revisión'],['antes','Antes / después'],['calidad','Calidad']];
    var h = '<div class="me-note">'+esc(NOTA)+'</div>';
    if(meses.length>1) h += '<label class="me-muted">Mes: <select id="me-mes">'+meses.map(function(m){return '<option value="'+m+'"'+(m===mes?' selected':'')+'>'+mesNom(m)+'</option>';}).join('')+'</select></label>';
    h += '<div class="me-tabs">'+tabs.map(function(t){return '<div class="me-tab'+(tab===t[0]?' on':'')+'" data-tab="'+t[0]+'">'+t[1]+'</div>';}).join('')+'</div>';
    h += tab==='cobertura'?vCobertura():tab==='revision'?vRevision():tab==='antes'?vAntes():vCalidad();
    root.innerHTML = h;
    root.querySelectorAll('.me-tab').forEach(function(el){ el.onclick=function(){ tab=el.dataset.tab; render(); }; });
    var sm = root.querySelector('#me-mes'); if(sm) sm.onchange=function(){ mes=sm.value; render(); };
    root.querySelectorAll('.me-sel').forEach(function(el){ el.onchange=function(){ est[el.dataset.id]=el.value; guardar(); render(); }; });
    root.querySelectorAll('[data-regla]').forEach(function(el){ el.onclick=function(){ filtroRegla = filtroRegla===el.dataset.regla ? '' : el.dataset.regla; render(); }; });
    var b1 = root.querySelector('#me-csv-rev'); if(b1) b1.onclick=function(){
      var f=[['Fecha','Asesor','Tipo de evento','Negocio','Empresa','NIT','Creado','Estado de revisión']];
      datos().candidatos.forEach(function(c){ c.items.forEach(function(it){ f.push([c.fecha,c.asesor,c.tipo_evento,it.deal_id,it.empresa,it.nit,it.creado,est[c.id]||'Pendiente']); }); });
      descargar('revision_visitas_'+mes+'.csv', f); };
    var b2 = root.querySelector('#me-csv-cal'); if(b2) b2.onclick=function(){
      var f=[['Regla','Negocio','Asesor','Fecha','Empresa','NIT','Detalle','Enlace']];
      datos().calidad.forEach(function(x){ f.push([x.regla,x.deal_id,x.asesor,x.fecha,x.empresa,x.nit,x.detalle,x.url]); });
      descargar('calidad_multiempresa_'+mes+'.csv', f); };
  }

  var nav = document.querySelector('.navitem[data-section="multiempresa"]');
  if(nav) nav.addEventListener('click', function(){
    document.querySelectorAll('.navitem').forEach(function(n){ n.classList.toggle('active', n.dataset.section==='multiempresa'); });
    document.querySelectorAll('.section').forEach(function(s){ s.classList.toggle('active', s.id==='sec-multiempresa'); });
    var sb=document.querySelector('nav.sidebar'); if(sb) sb.classList.remove('open');
    render();
  });
})();
</script>
"""


def inyectar(html):
    if MARCA in html:
        return html
    if 'DATA.multiempresa' in html:   # por si el master ya lo trae
        pass
    n_head = html.count('</head>')
    html = html.replace('</head>', CSS + '</head>', 1) if n_head else html
    # item de menu: antes del primer </nav>
    i = html.index('</nav>')
    html = html[:i] + '    ' + NAV_ITEM + '\n  ' + html[i:]
    # seccion: antes del primer </main>
    j = html.index('</main>')
    html = html[:j] + SECTION + '  ' + html[j:]
    # script: antes del ultimo </body>
    k = html.rindex('</body>')
    html = html[:k] + JS + html[k:]
    return html


def aplicar_a_archivo(path):
    with open(path, encoding='utf-8') as f:
        h = f.read()
    h2 = inyectar(h)
    if h2 != h:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(h2)
        print(f'  [multiempresa] seccion inyectada en {path}')
