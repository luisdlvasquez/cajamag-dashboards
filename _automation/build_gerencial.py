import glob, os, sys
import json, re

_env_base = os.environ.get("PIPELINE_BASE_DIR")
if _env_base:
    SRC = f"{_env_base}/_automation/Dashboard_Master_DATA.html"
    OUT = f"{os.environ.get('PIPELINE_OUT_DIR', _env_base + '/_out')}/Dashboard_Gerencial_CER.html"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
else:
    _candidates = glob.glob("/sessions/*/mnt/Trabajando Juntos")
    if not _candidates:
        print("ERROR: no se encontro la carpeta 'Trabajando Juntos' montada bajo /sessions/*/mnt/")
        sys.exit(1)
    _mnt = os.path.dirname(_candidates[0])
    SRC = f"{_candidates[0]}/CAJAMAG/02_DASHBOARDS/_automation/Dashboard_Master_DATA.html"
    OUT = f"{_mnt}/outputs/Dashboard_Gerencial_CER.html"

html = open(SRC, encoding='utf-8').read()

# ---------- 1. Parse DATA ----------
d_start = html.index('const DATA = ') + len('const DATA = ')
d_end = html.index('function fmt(n)')
blob = html[d_start:d_end].strip()
assert blob.endswith(';')
blob = blob[:-1]
DATA = json.loads(blob)

data_min = {k: v for k, v in DATA.items() if k not in ('analisis_cruzado', 'historia_asesor')}
new_data_json = json.dumps(data_min, ensure_ascii=False, separators=(',', ':'))
print("Original DATA blob chars:", len(blob), "-> gerencial minimized:", len(new_data_json))

# ---------- 2. Head/CSS unchanged ----------
head = html[:html.index('<body>')]

# ---------- 3. Body markup ----------
body_start = html.index('<body>')
sec_hist_start = html.index('<!-- ===================== HISTORIA COMERCIAL DEL ASESOR ===================== -->')
main_close = html.index('</section>\n  </main>') + len('</section>')
script_open = html.index('<script>', main_close)

header_html = html[body_start:html.index('<div class="health-strip"')]
health_div, hd_i = re.search(r'<div class="health-strip"[^>]*></div>\n', html).group(), None
nav_and_resumen_open = html[html.index('<div class="health-strip"'): html.index('<!-- ===================== RESUMEN ===================== -->')]

gerencial_sections = html[html.index('<!-- ===================== RESUMEN ===================== -->'): sec_hist_start]

# Trim nav to only the 4 gerencial items (drop navsep + historia/hechos items)
nav_m = re.search(r'<nav class="sidebar">.*?</nav>', nav_and_resumen_open, re.S)
new_nav = '''<nav class="sidebar">
    <div class="navitem active" data-section="resumen"><span class="ic">🏠</span>Resumen</div>
    <div class="navitem" data-section="gestion"><span class="ic">📋</span>Gestión</div>
    <div class="navitem" data-section="empresas"><span class="ic">🏢</span>Empresas</div>
    <div class="navitem" data-section="ventas"><span class="ic">💰</span>Ventas</div>
    <div class="navitem" data-section="contrato"><span class="ic">🎯</span>Contrato</div>
  </nav>'''
nav_new = nav_and_resumen_open[:nav_m.start()] + new_nav + nav_and_resumen_open[nav_m.end():]

new_header = header_html.replace(
    'CAJAMAG — Dashboard Operativo</h1><div class="sub">Para seguimiento comercial y operativo — Gestiones, Empresas, Ventas e Historia Comercial del Asesor</div>',
    'CAJAMAG — Dashboard Gerencial</h1><div class="sub">Resumen, Gestión, Empresas y Ventas frente a metas contractuales — vista privada</div>'
)
new_header = new_header.replace(
    '<span class="opt-tag">Análisis Cruzado — Segmentación completa</span>',
    '<span class="opt-tag">Vista Gerencial — Acceso restringido</span>'
)

body_new = new_header + nav_new + gerencial_sections + "\n  </main>\n</div>\n\n"

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
resumen_cumpl_js, _, _ = cut(script_full, '// ================= RESUMEN: cumplimiento vs metas contractuales =================', '// ================= ÚLTIMOS HECHOS =================')

new_script = (
    helpers + nav_js +
    health_js + resumen_js + gestion_js + empresas_js + ventas_js +
    resumen_cumpl_js
)

# ---------- 5. Password gate wrapper ----------
GATE = '''<div id="gate-overlay" style="position:fixed;inset:0;z-index:99999;background:linear-gradient(135deg,#004d45,#00685E);display:flex;align-items:center;justify-content:center;font-family:'Montserrat',system-ui,sans-serif;">
  <div style="background:#fff;border-radius:16px;padding:36px 34px;width:340px;max-width:90vw;box-shadow:0 20px 50px rgba(0,0,0,.3);text-align:center;">
    <div style="font-size:30px;margin-bottom:6px;">🔒</div>
    <h2 style="font-size:17px;font-weight:800;color:#004d45;margin-bottom:4px;">Vista Gerencial — CAJAMAG</h2>
    <p style="font-size:12px;color:#5B6770;margin-bottom:18px;">Acceso restringido. Ingresa la contraseña para continuar.</p>
    <input type="password" id="gate-pw" placeholder="Contraseña" style="width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #d8dbe0;border-radius:8px;font-size:14px;margin-bottom:10px;" autocomplete="off">
    <div id="gate-err" style="display:none;color:#d64545;font-size:11.5px;margin-bottom:10px;">Contraseña incorrecta.</div>
    <button id="gate-btn" style="width:100%;padding:10px;border:none;border-radius:8px;background:#00685E;color:#fff;font-weight:700;font-size:14px;cursor:pointer;">Entrar</button>
  </div>
</div>
<div id="gate-content" style="display:none;">
'''

CLOSING_SCRIPT = '''
</div>
<script>
(function(){
  var HASH = 940571663; // huella del password, no es el password en si
  function simpleHash(str){
    var h = 5381;
    for(var i=0;i<str.length;i++){ h = ((h*33) ^ str.charCodeAt(i)) >>> 0; }
    h = ((h ^ (h>>>15)) * 2246822519) >>> 0;
    h = ((h ^ (h>>>13)) * 3266489917) >>> 0;
    h = (h ^ (h>>>16)) >>> 0;
    return h % 999999999;
  }
  function tryUnlock(){
    var pw = document.getElementById('gate-pw').value;
    if(simpleHash(pw) === HASH){
      document.getElementById('gate-overlay').style.display = 'none';
      document.getElementById('gate-content').style.display = '';
      try{ sessionStorage.setItem('cer_gerencial_ok','1'); }catch(e){}
    } else {
      document.getElementById('gate-err').style.display = 'block';
    }
  }
  document.getElementById('gate-btn').addEventListener('click', tryUnlock);
  document.getElementById('gate-pw').addEventListener('keydown', function(e){ if(e.key==='Enter') tryUnlock(); });
  try{
    if(sessionStorage.getItem('cer_gerencial_ok')==='1'){
      document.getElementById('gate-overlay').style.display = 'none';
      document.getElementById('gate-content').style.display = '';
    }
  }catch(e){}
})();
</script>
'''

# ---------- 6. Assemble ----------
new_html = (
    head + "<body>\n" + GATE +
    body_new.replace('<body>\n', '', 1) +
    "<script>\nconst DATA = " + new_data_json + ";\n" + new_script + "</script>\n" +
    CLOSING_SCRIPT +
    "\n</body>\n</html>\n"
)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(new_html)

print("Wrote", OUT, "size:", len(new_html))

# ---------- 7. Mobile CSS + tabla Resumen Consolidado (baked in) ----------
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

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
if "</style>" in final_html:
    final_html = final_html.replace("</style>", mobile_css + "</style>", 1)

table_html = '''
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>\U0001F4CA Resumen consolidado por asesor</span></div>
          <div class="section-desc">Todo en una sola tabla: zona, ventas, gestión y empresas — para revisar de un vistazo.</div>
          <div class="table-scroll">
          <table><thead><tr><th>Asesor</th><th>Zona</th><th>Estado</th><th>Meses activo</th><th>Ventas ejecutadas</th><th>% Cumpl. ventas</th><th>% Cumpl. gestión</th><th>Empresas gestionadas</th><th>Empresas faltantes</th></tr></thead><tbody id="tblResumenConsolidado"></tbody></table>
          </div>
        </div>
'''
anchor_table = '''          <table><thead><tr><th>Asesor</th><th>Meses activo</th><th>% Cumpl. gestión</th><th>Estado</th></tr></thead><tbody id="tblResumenGestionMeta"></tbody></table>
          </div>
        </div>
      </div>
    </section>'''
if anchor_table in final_html:
    final_html = final_html.replace(anchor_table, '''          <table><thead><tr><th>Asesor</th><th>Meses activo</th><th>% Cumpl. gestión</th><th>Estado</th></tr></thead><tbody id="tblResumenGestionMeta"></tbody></table>
          </div>
        </div>
''' + table_html + '''      </div>
    </section>''')

# ---------- 7b. Resumen KPI: fechas dinamicas (ya no fijas en mar-jul) ----------
old_resumen_kpis_js_g = '''document.getElementById('resumenKpis').innerHTML = `
  <div class="kpi"><div class="kv">${contractAvgPct.toFixed(0)}%</div><div class="kl">Cumplimiento contractual (Gestión)</div></div>
  <div class="kpi acc"><div class="kv">${fmtM(ventasD.total_ejecutado_5m)}</div><div class="kl">Ventas ejecutadas mar-jul</div></div>
  <div class="kpi"><div class="kv">${fmtM(ventasD.meta_ejecutado_5m)}</div><div class="kl">Meta proyectada mar-jul (${ventasD.cumpl_ejecutado_5m_pct}% cumplido)</div></div>
  <div class="kpi"><div class="kv">${DATA.empresas_agg.per_counts['Contactada - contrato actual']||0}</div><div class="kl">Empresas contactadas (contrato actual)</div></div>
  <div class="kpi bad"><div class="kv">${DATA.empresas_agg.per_counts['No contactada']||0}</div><div class="kl">Empresas no contactadas</div></div>
`;'''
new_resumen_kpis_js_g = '''// 3-sep-2026, a pedido de Luis: esta tarjeta suma TODO el rango de tendencia (marzo a la
// fecha), incluyendo marzo -- marzo tiene su propia meta real (prorateada, ~60.3M, no la
// tasa plana de 98.3M/mes de abril-septiembre) y debe contarse. Este acumulado NO lleva
// ningun factor extra (el +25% es exclusivo de Operativo, nunca de Gerencial): es la suma
// llana de las metas reales mes a mes que ya trae ventasD.tendencia.
const mesesTendenciaG = ventasD.tendencia.map(t=>t.mes);
const rangoTendenciaG = mesesTendenciaG.length? (mesesTendenciaG[0]+'-'+mesesTendenciaG[mesesTendenciaG.length-1]) : '';
const acumEjecutadoG = ventasD.tendencia.reduce((s,t)=>s+t.ventas,0);
const acumMetaG = ventasD.tendencia.reduce((s,t)=>s+t.meta,0);
const pctAcumG = acumMetaG>0 ? (acumEjecutadoG/acumMetaG*100) : 0;
document.getElementById('resumenKpis').innerHTML = `
  <div class="kpi"><div class="kv">${contractAvgPct.toFixed(0)}%</div><div class="kl">Cumplimiento contractual (Gestión)</div></div>
  <div class="kpi acc"><div class="kv">${fmtM(acumEjecutadoG)}</div><div class="kl">Ventas ejecutadas ${rangoTendenciaG}</div></div>
  <div class="kpi"><div class="kv">${fmtM(acumMetaG)}</div><div class="kl">Meta acumulada ${rangoTendenciaG} (${pctAcumG.toFixed(0)}% ejecutado)</div></div>
  <div class="kpi"><div class="kv">${DATA.empresas_agg.per_counts['Contactada - contrato actual']||0}</div><div class="kl">Empresas contactadas (contrato actual)</div></div>
  <div class="kpi bad"><div class="kv">${DATA.empresas_agg.per_counts['No contactada']||0}</div><div class="kl">Empresas no contactadas</div></div>
`;'''
if old_resumen_kpis_js_g in final_html:
    final_html = final_html.replace(old_resumen_kpis_js_g, new_resumen_kpis_js_g)
    print("Paso 7b aplicado: Resumen Gerencial -- fechas dinamicas (ya no fijas en mar-jul).")
else:
    print("ADVERTENCIA: no se encontro el bloque resumenKpis esperado en Gerencial; revisar manualmente.")

anchor_js = '''  document.getElementById('tblResumenGestionMeta').innerHTML = rowsGes.map(r=>{
    const cls = statusClass(r.pct);
    return `<tr><td>${r.name}</td><td>${r.meses}</td><td><span class="badge ${cls||'ok'}">${r.pct.toFixed(0)}%</span></td><td><span class="badge ${r.active===false?'off':'on'}">${r.active===false?'Inactivo':'Activo'}</span></td></tr>`;
  }).join('');
})();'''
new_js = '''  document.getElementById('tblResumenGestionMeta').innerHTML = rowsGes.map(r=>{
    const cls = statusClass(r.pct);
    return `<tr><td>${r.name}</td><td>${r.meses}</td><td><span class="badge ${cls||'ok'}">${r.pct.toFixed(0)}%</span></td><td><span class="badge ${r.active===false?'off':'on'}">${r.active===false?'Inactivo':'Activo'}</span></td></tr>`;
  }).join('');

  const rowsCons = advisorsFull.map(a=>{
    const rv = ventasRankByName[a.name] || {};
    const pctVentas = rv.meta_acumulada_5m ? (rv.total_acumulado/rv.meta_acumulada_5m*100) : null;
    const pctGestion = a.accumulated.global_pct*100;
    return {
      name: a.name, zona: rv.zona || '—', active: a.active, meses: a.meses_activos,
      ventas: rv.total_acumulado||0, pctVentas, pctGestion,
      gestionadas: a.empresas_gestionadas_contrato||0, faltantes: a.empresas_faltantes_contrato||0,
    };
  }).sort((a,b)=>(b.pctGestion||0)-(a.pctGestion||0));
  document.getElementById('tblResumenConsolidado').innerHTML = rowsCons.map(r=>{
    const clsV = r.pctVentas!=null? statusClass(r.pctVentas):'na';
    const clsG = statusClass(r.pctGestion);
    return `<tr><td>${r.name}</td><td>${r.zona}</td><td><span class="badge ${r.active===false?'off':'on'}">${r.active===false?'Inactivo':'Activo'}</span></td><td>${r.meses}</td><td>${fmt(r.ventas)}</td><td><span class="badge ${clsV||'ok'}">${r.pctVentas!=null?r.pctVentas.toFixed(0)+'%':'—'}</span></td><td><span class="badge ${clsG||'ok'}">${r.pctGestion.toFixed(0)}%</span></td><td>${r.gestionadas}</td><td>${r.faltantes}</td></tr>`;
  }).join('');
})();'''
if anchor_js in final_html:
    final_html = final_html.replace(anchor_js, new_js)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("mobile CSS + tabla consolidada aplicados")

# ---------- 8. Hoja 'Contrato' (vision estrategica, 27-ago-2026, a pedido de Luis) ----------
# Objetivo de Luis: el Gerencial debe verse mas hacia lo contractual/estrategico
# (Operativo ya cubre el dia a dia). Se agrega una hoja nueva y propia, ubicada AL
# FINAL del nav (despues de Ventas, a pedido de Luis), que muestra el avance real
# vs. TODAS las metas del contrato VIGENTE de 6 meses (meta_6m x elapsed_fraction).
# IMPORTANTE (correccion de Luis, 27-ago-2026): el contrato de 11 meses/meta_11m
# AUN NO se ha firmado -- hoy solo existe el de 6 meses. Por eso la vista NO usa
# meta_11m/elapsed_fraction_annual como referencia principal (esos campos quedan
# en el DATA por si se necesitan el dia que se firme el contrato anual, pero no
# se muestran en esta hoja). Se elimina el subtab viejo 'Contrato Cajamag' de
# Gestion (quedaria duplicado).
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

# 8a. Nav: ya se agrego el item 'Contrato' en new_nav (arriba). Aqui solo falta
# el subtab de Gestion y la seccion HTML + JS.

# 8b. Quitar el subtab 'Contrato Cajamag' de Gestion (nav interno + panel)
old_nav_gsub_full = '''      <div class="subtabs">
        <div class="subtab active" data-gsub="equipo">Equipo</div>
        <div class="subtab" data-gsub="asesor">Por Asesor</div>
        <div class="subtab" data-gsub="contrato">Contrato Cajamag</div>
      </div>'''
new_nav_gsub_full = '''      <div class="subtabs">
        <div class="subtab active" data-gsub="equipo">Equipo</div>
        <div class="subtab" data-gsub="asesor">Por Asesor</div>
      </div>'''
if old_nav_gsub_full in final_html:
    final_html = final_html.replace(old_nav_gsub_full, new_nav_gsub_full)
    print("Paso 8b: subtab 'Contrato Cajamag' quitado de Gestion (ahora vive en su propia hoja).")
else:
    print("ADVERTENCIA: no se encontro el subtab-nav de Gestion (Contrato Cajamag) a quitar.")

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
if old_gsub_contrato in final_html:
    final_html = final_html.replace(old_gsub_contrato, new_gsub_contrato)
    print("Paso 8b: panel 'gsub-contrato' quitado de Gestion.")
else:
    print("ADVERTENCIA: no se encontro el panel gsub-contrato a quitar.")

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
if old_contrato_js in final_html:
    final_html = final_html.replace(old_contrato_js, "// (Subtab Contrato Cajamag movido a su propia hoja 'Contrato' -- 27-ago-2026)")
    print("Paso 8b: JS viejo de Contrato Cajamag removido.")
else:
    print("ADVERTENCIA: no se encontro el JS viejo de Contrato Cajamag a quitar.")

# 8c. Insertar la seccion HTML nueva 'Contrato', AL FINAL (despues de Ventas), a pedido
# de Luis (27-ago-2026). El contrato vigente HOY es el de 6 meses (no el anual de 11
# meses -- ese es solo una referencia de a donde se llegaria SI se firma un contrato
# completo, aclarado por Luis) -- por eso la vista principal se mide contra el
# checkpoint de 6 meses (meta_6m x elapsed_fraction), no contra meta_11m.
anchor_seccion = '''        <table><thead><tr><th>Fecha</th><th>Mes</th><th>Asesor</th><th>Zona</th><th>Tipo</th><th>Servicio</th><th>Cliente</th><th>NIT/CC</th><th>Empresa</th><th>Detalle</th><th>Cantidad</th><th>Valor</th><th>Fuente</th></tr></thead><tbody id="tblVentas"></tbody></table>
        </div>
      </div>
    </section>'''
seccion_contrato = '''        <table><thead><tr><th>Fecha</th><th>Mes</th><th>Asesor</th><th>Zona</th><th>Tipo</th><th>Servicio</th><th>Cliente</th><th>NIT/CC</th><th>Empresa</th><th>Detalle</th><th>Cantidad</th><th>Valor</th><th>Fuente</th></tr></thead><tbody id="tblVentas"></tbody></table>
        </div>
      </div>
    </section>

    <!-- ===================== CONTRATO ===================== -->
    <section class="section" id="sec-contrato">
      <div class="section-title">Cómo vamos frente al Contrato</div>
      <div class="section-desc">Vista estratégica: avance real vs. las metas del contrato vigente (6 meses) al ritmo esperado a la fecha de corte.</div>
      <div class="kpi-grid" id="contratoKpis"></div>
      <div class="card" id="contratoRiesgoCard" style="display:none;">
        <div class="card-title"><span><span class="dot"></span>⚠️ Indicadores por debajo del ritmo esperado (&lt;80%)</span></div>
        <div class="hca-ind-grid" id="contratoRiesgoList"></div>
      </div>
      <div id="contratoCategorias"></div>
    </section>'''
if anchor_seccion in final_html:
    final_html = final_html.replace(anchor_seccion, seccion_contrato)
    print("Paso 8c: seccion HTML 'Contrato' insertada (al final, despues de Ventas).")
else:
    print("ADVERTENCIA: no se encontro el anchor de fin de Ventas para insertar Contrato.")

# 8d. JS de la hoja nueva: se agrega al final del script principal (antes del cierre
# </script> que precede al GATE/password script), reutilizando contract/contractIndicatorsAll
# ya definidos en el bloque HEALTH STRIP (arriba en el mismo <script>).
contrato_js = '''
// ================= CONTRATO (vista estrategica, hoja nueva -- medido contra el
// contrato VIGENTE de 6 meses, aclarado por Luis el 27-ago-2026: el de 11 meses
// aun no se ha firmado, asi que no se usa como referencia principal) =================
(function(){
  const allIndsC = contract.categories.flatMap(cat=>cat.indicators.map(i=>Object.assign({categoria:cat.name}, i)));
  const activeIndsC = allIndsC.filter(i=>!i.pending && i.meta_6m);

  const hoyC = new Date(contract.data_cutoff);
  const finC = new Date(contract.period_end);
  const diasRestantesC = Math.max(Math.round((finC-hoyC)/86400000),0);
  const pctTiempoC = (contract.elapsed_fraction||0)*100;

  const pctList = activeIndsC.map(i=>{
    const esperado = i.meta_6m*contract.elapsed_fraction;
    return esperado>0 ? Math.min(i.real/esperado*100,150) : 0;
  });
  const pctPromedioC = pctList.length ? pctList.reduce((s,p)=>s+p,0)/pctList.length : 0;
  const clsGlobalC = statusClass(Math.min(pctPromedioC,100));
  const ventasInd = allIndsC.find(i=>i.name==='Ventas efectivas totales ($)');

  document.getElementById('contratoKpis').innerHTML = `
    <div class="kpi"><div class="kv">${pctTiempoC.toFixed(0)}%</div><div class="kl">Tiempo transcurrido del contrato vigente (6 meses)</div></div>
    <div class="kpi"><div class="kv">${diasRestantesC}</div><div class="kl">Días restantes hasta el cierre (${finC.toLocaleDateString('es-CO')})</div></div>
    <div class="kpi ${clsGlobalC==='bad'?'bad':(clsGlobalC==='warn'?'':'acc')}"><div class="kv">${pctPromedioC.toFixed(0)}%</div><div class="kl">Cumplimiento promedio vs. ritmo esperado (todos los indicadores)</div></div>
    <div class="kpi"><div class="kv">${ventasInd?fmtM(ventasInd.real):'—'}</div><div class="kl">Ventas ejecutadas del contrato (marzo a la fecha)</div></div>
  `;

  const riesgosC = activeIndsC.map(i=>{
    const esperado = i.meta_6m*contract.elapsed_fraction;
    const pct = esperado>0 ? i.real/esperado*100 : 0;
    return Object.assign({}, i, {pct, esperado});
  }).filter(i=>i.pct<80).sort((a,b)=>a.pct-b.pct);
  if (riesgosC.length){
    document.getElementById('contratoRiesgoCard').style.display='';
    document.getElementById('contratoRiesgoList').innerHTML = riesgosC.map(i=>`
      <div class="hca-ind-card"><div class="hi-top"><span class="hi-name">${i.categoria} — ${i.name}</span><span class="hi-pct">${i.pct.toFixed(0)}%</span></div>
      <div class="hi-track"><div class="hi-fill bad" style="width:${Math.min(i.pct,100)}%"></div></div>
      <div class="hi-meta">${i.name.includes('($)')?fmtM(i.real):fmtN(i.real)} de ${i.name.includes('($)')?fmtM(i.esperado):fmtN(Math.round(i.esperado))} esperado a la fecha (meta del contrato: ${i.name.includes('($)')?fmtM(i.meta_6m):fmtN(i.meta_6m)})</div></div>
    `).join('');
  }

  document.getElementById('contratoCategorias').innerHTML = contract.categories.map(cat=>{
    const rows = cat.indicators.map(i=>{
      if (i.pending) return `<tr><td>${i.name}</td><td colspan="4" style="color:var(--text-muted);">Sin fuente de datos aún</td></tr>`;
      const esperado = i.meta_6m*contract.elapsed_fraction;
      const pct = esperado>0 ? i.real/esperado*100 : 0;
      const cls = statusClass(Math.min(pct,100));
      const isVal = i.name.includes('($)');
      const f = isVal ? fmtM : fmtN;
      return `<tr><td>${i.name}${i.partial?' *':''}</td><td>${f(i.real)}</td><td>${f(Math.round(esperado))}</td><td>${f(i.meta_6m)}</td><td><span class="badge ${cls||'ok'}">${pct.toFixed(0)}%</span></td></tr>`;
    }).join('');
    return `<div class="card">
      <div class="card-title"><span><span class="dot"></span>${cat.name}</span></div>
      <div class="table-scroll">
      <table><thead><tr><th>Indicador</th><th>Real</th><th>Ritmo esperado a la fecha</th><th>Meta contrato (6m)</th><th>% vs. ritmo</th></tr></thead><tbody>${rows}</tbody></table>
      </div>
    </div>`;
  }).join('');
})();
'''
closing_anchor = "</script>\n\n</div>\n<script>\n(function(){\n  var HASH ="
if closing_anchor in final_html:
    final_html = final_html.replace(closing_anchor, contrato_js + closing_anchor)
    print("Paso 8d: JS de la hoja 'Contrato' agregado (dentro del script principal).")
else:
    print("ADVERTENCIA: no se encontro el anchor de cierre para insertar el JS de Contrato.")

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 8 completo: hoja 'Contrato' (vista estrategica) agregada a Gerencial.")

# ---------- 9. Ventas: arreglar grafica 'Ranking de servicios' (27-ago-2026, a pedido de Luis) ----------
# Gerencial nunca aplico el catalogo oficial de 29 servicios que Operativo si
# aplica en su propio Paso 10 (build_operativo.py). Por eso la grafica de
# Ranking de servicios en Ventas se armaba con el campo crudo 'servicio' (118
# valores distintos por typos/variantes: "IFT", "Teyuna", "Cinemark" sueltos,
# etc.), en vez del servicio oficial normalizado. Se reutiliza EXACTAMENTE la
# misma logica de resolucion que ya esta probada en Operativo (incl. el fix
# de "SEGURO DE VIDA" -> Turismo por zona, 27-ago-2026), aplicada aqui solo al
# filtro 'Servicio' y a la grafica de ranking (la tabla de Detalle se deja
# mostrando el campo crudo, que es informacion util a nivel de fila).
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_populate_servicio_g = '''populateSelect('fVenServicio', ventasD.filtros.servicios);

let chVentasTendencia, chVentasServicio, chVentasTipo;'''
new_populate_servicio_g = '''// ---- Catálogo OFICIAL de servicios + IVA (mismo catálogo/resolución que Dashboard Operativo) ----
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
});

populateSelect('fVenServicio', [...new Set(ventasD.transacciones.map(r=>r.servicio_oficial))].sort());

let chVentasTendencia, chVentasServicio, chVentasTipo;'''
assert old_populate_servicio_g in final_html, "No se encontro populateSelect fVenServicio (Gerencial)"
final_html = final_html.replace(old_populate_servicio_g, new_populate_servicio_g)

old_filtro_servicio_g = '''  if (servicio) rows = rows.filter(r=>r.servicio===servicio);'''
new_filtro_servicio_g = '''  if (servicio) rows = rows.filter(r=>r.servicio_oficial===servicio);'''
assert old_filtro_servicio_g in final_html, "No se encontro el filtro de servicio (Gerencial)"
final_html = final_html.replace(old_filtro_servicio_g, new_filtro_servicio_g)

old_ranking_serv_g = '''  const servMap = {};
  rows.forEach(r=>{ servMap[r.servicio] = (servMap[r.servicio]||0) + r.valor; });'''
new_ranking_serv_g = '''  const servMap = {};
  rows.forEach(r=>{ servMap[r.servicio_oficial] = (servMap[r.servicio_oficial]||0) + r.valor; });'''
assert old_ranking_serv_g in final_html, "No se encontro el ranking de servicios (Gerencial)"
final_html = final_html.replace(old_ranking_serv_g, new_ranking_serv_g)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 9 aplicado: Ventas -- grafica 'Ranking de servicios' y filtro 'Servicio' ahora usan el catalogo oficial de 29 servicios (mismo criterio que Operativo), en vez del campo crudo con 118 variantes/typos.")

# ---------- 9b. Ventas: Cumplimiento de Meta por Servicio (9-sep-2026, a pedido de Luis) ----------
# Luis subio CAJAMAG/meta cer 2026.xlsx: la meta contractual de $590.000.000 (la
# misma meta total del contrato, ver pipeline_master.py seccion 5) desglosada por
# servicio/centro de costos via 'Participacion CER'. Se compara el vendido
# acumulado de TODO el contrato por servicio oficial (mismo catalogo/resolucion
# del Paso 9, sin filtro de zona/asesor -- la meta es del equipo completo) contra
# esa meta por servicio, para ver cuales servicios estan mas o menos vendidos y
# su % de cumplimiento. Nota: 2 nombres del archivo de Luis venian truncados por
# Excel ("BIBLIOTECA STA MTA" y "UNIDAD DE CULTURA Y COMUNICACI") -- se usan aqui
# con el nombre completo del catalogo oficial (mismo centro de costos). El
# servicio "ADULTO MAYOR" del catalogo oficial no aparece en el archivo de Luis
# (no tiene meta asignada) -- se muestra igual, marcado "Sin meta asignada".
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_cumpl_anchor = '''      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ranking de servicios — todos (según filtro)</span></div>
        <div class="chart-box" style="height:620px;"><canvas id="chVentasServicio"></canvas></div>
      </div>
      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Por tipo de venta</span></div>'''
new_cumpl_anchor = '''      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ranking de servicios — todos (según filtro)</span></div>
        <div class="chart-box" style="height:620px;"><canvas id="chVentasServicio"></canvas></div>
      </div>
      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Cumplimiento de Meta por Servicio (contrato completo a la fecha, sin filtro)</span></div>
        <div style="font-size:12px;color:var(--text-muted);margin:-4px 0 10px;">Meta: distribución oficial de los $590.000.000 del contrato por servicio (archivo "meta cer 2026.xlsx"). No aplica el filtro de arriba — es la meta del equipo completo.</div>
        <div class="table-scroll">
        <table id="tblCumplimientoServicio"><thead><tr><th>Servicio</th><th>Vendido (contrato completo)</th><th>Meta contrato</th><th>% Cumplimiento</th><th>Diferencia</th></tr></thead><tbody></tbody></table>
        </div>
      </div>
      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Por tipo de venta</span></div>'''
assert old_cumpl_anchor in final_html, "No se encontro el anclaje HTML para insertar Cumplimiento de Meta por Servicio"
final_html = final_html.replace(old_cumpl_anchor, new_cumpl_anchor)

old_forEach_servicio = '''ventasD.transacciones.forEach(r=>{
  const oficial = resolverServicioOficial(r);
  r.servicio_oficial = oficial || 'Sin clasificar (revisar)';
});

populateSelect('fVenServicio', [...new Set(ventasD.transacciones.map(r=>r.servicio_oficial))].sort());'''
assert old_forEach_servicio in final_html, "No se encontro el forEach de servicio_oficial (Gerencial)"

new_forEach_servicio = old_forEach_servicio + '''

// ---- Cumplimiento de Meta por Servicio (9-sep-2026) ----
// Meta contractual de $590.000.000 desglosada por servicio (archivo "meta cer 2026.xlsx", provisto por Luis).
// Los 2 nombres que Excel truncaba se dejan aqui con el nombre completo del catalogo oficial.
const META_SERVICIO_CER2026 = {
  'VACUNACION SANTA MARTA': 29913000,
  'CAPACITACION SANTA MARTA': 35099100,
  'CAPACITACION CIENAGA': 5900000,
  'CAPACITACION FUNDACION': 3816521.875159,
  'CAPACITACION PIVIJAY': 118000,
  'INST. FORMACION TECNICO': 112124378.125,
  'INST. FORMACION TECN CIENAGA': 295000,
  'INST. FORMACION TECN FUNDACION': 236000,
  'INST. FORMACION TECNICO PIVIJA': 295000,
  'CAP ESCUELA MUSICAL SANTA MARTA': 1770000,
  'BIBLIOTECA SANTA MTA': 7080000,
  'UNIDAD DE CULTURA Y COMUNICACION': 59000,
  'TEATRO CAJAMAG': 8850000,
  'RECREACION. STA MTA': 123900000,
  'RECREACION CIENAGA': 1593000,
  'RECREACION FUNDAC.': 885000,
  'CENTRO RECREC.TEYUNA': 51920000,
  'CAFETERIA TEYUNA': 53100000,
  'DEPORTES STA MTA': 5900000,
  'DEPORTES CIENAGA': 295000,
  'DEPORTES FUNDACION .': 1947000,
  'RECREACION PIVIJAY': 118000,
  'CENTRO RECREACIONAL CIENAGA': 3776000,
  'CENTRO RECREACIONAL FUNDACION': 4130000,
  'TURISMO SOCIAL STA MARTA': 135700000,
  'TURISMO SOCIAL CIENAGA': 826000,
  'TURISMO SOCIAL FUNDACION': 177000,
  'TURISMO SOCIAL PIVIJAY': 177000,
};
function renderCumplimientoServicios(){
  const tbody = document.querySelector('#tblCumplimientoServicio tbody');
  if (!tbody) return;
  const agg = {};
  ventasD.transacciones.forEach(r=>{ agg[r.servicio_oficial] = (agg[r.servicio_oficial]||0) + (r.valor||0); });
  const claves = new Set([...Object.keys(META_SERVICIO_CER2026), ...Object.keys(agg)]);
  let rows = [...claves].map(s=>{
    const vendido = agg[s]||0;
    const meta = META_SERVICIO_CER2026[s];
    const pct = (meta!=null && meta>0) ? (vendido/meta*100) : null;
    return {servicio:s, vendido, meta, pct};
  });
  rows.sort((a,b)=>{
    if (a.pct==null && b.pct==null) return b.vendido-a.vendido;
    if (a.pct==null) return 1;
    if (b.pct==null) return -1;
    return a.pct-b.pct;
  });
  tbody.innerHTML = rows.map(r=>{
    const cls = r.pct!=null ? statusClass(r.pct) : 'na';
    const pctTxt = r.pct!=null ? r.pct.toFixed(0)+'%' : 'Sin meta asignada';
    const metaTxt = r.meta!=null ? fmt(r.meta) : '—';
    const difTxt = r.meta!=null ? fmt(r.vendido-r.meta) : '—';
    return `<tr><td>${r.servicio}</td><td>${fmt(r.vendido)}</td><td>${metaTxt}</td><td><span class="badge ${cls||'ok'}">${pctTxt}</span></td><td>${difTxt}</td></tr>`;
  }).join('');
}
renderCumplimientoServicios();'''
final_html = final_html.replace(old_forEach_servicio, new_forEach_servicio)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 9b aplicado: Ventas -- nueva tabla 'Cumplimiento de Meta por Servicio' (vendido acumulado del contrato vs. meta por servicio del archivo meta cer 2026.xlsx), sin filtro (meta de equipo completo).")


# ---------- 10. Ventas: ocultar nota "Fuente combinada" (27-ago-2026, a pedido de Luis) ----------
# Mismo pedido que ya se aplico en Operativo (Paso 13 de build_operativo.py):
# "no me genera valor" -- se oculta el cuadro tecnico de trazabilidad de
# fuentes (marzo-julio dataframe vs Bitrix IFT vs Panaca manual). Se habia
# aplicado solo en Operativo; Gerencial nunca recibio el mismo fix porque
# cada build script trabaja sobre su propia copia del template. Se oculta
# via CSS (display:none) en vez de borrar la logica que la llena.
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()
old_ventas_nota_g = '''      <div class="note" id="ventasNota"></div>'''
new_ventas_nota_g = '''      <div class="note" id="ventasNota" style="display:none;"></div>'''
assert old_ventas_nota_g in final_html, "No se encontro el div ventasNota (Gerencial)"
final_html = final_html.replace(old_ventas_nota_g, new_ventas_nota_g)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 10 aplicado: Ventas -- nota 'Fuente combinada' oculta (display:none), igual que en Operativo.")


# ---------- 7c. Resumen: mismo diseno unificado que Operativo (31-ago-2026, a pedido de Luis, docx "cambios hoja de resumen") ----------
# Reemplaza las 3 tablas viejas (VentasMeta/GestionMeta/Consolidado) por: tarjetas mes en curso,
# 4 cuadros categoria x mes (Gestion/Medios/Ventas por servicio/Empresas por tamano) con tendencia,
# y la tabla de Ejecucion de Ventas por asesor +2 columnas (mes en curso + total) -- igual que en
# Operativo. El selector "Contrato actual/pasado" queda pendiente (Luis: se alimenta despues de
# terminar de modificar todos los tableros).
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_html_7c = 'grid" id="resumenKpis"></div>\n      <div class="grid2">\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Ventas ejecutadas — tendencia marzo a la fecha</span></div>\n          <div class="chart-box"><canvas id="chResumenTendencia"></canvas></div>\n        </div>\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Empresas por estado de contacto</span></div>\n          <div class="chart-box"><canvas id="chResumenEmpresas"></canvas></div>\n        </div>\n      </div>\n\n      <div class="grid2">\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Cumplimiento vs. meta contractual — Ventas (por asesor)</span></div>\n          <div class="table-scroll">\n          <table><thead><tr><th>Asesor</th><th>Meses activo</th><th>Ejecutado</th><th>Meta a la fecha</th><th>% Cumpl.</th></tr></thead><tbody id="tblResumenVentasMeta"></tbody></table>\n          </div>\n        </div>\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Cumplimiento vs. meta contractual — Gestiones (por asesor)</span></div>\n          <div class="table-scroll">\n          <table><thead><tr><th>Asesor</th><th>Meses activo</th><th>% Cumpl. gestión</th><th>Estado</th></tr></thead><tbody id="tblResumenGestionMeta"></tbody></table>\n          </div>\n        </div>\n\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>📊 Resumen consolidado por asesor</span></div>\n          <div class="section-desc">Todo en una sola tabla: zona, ventas, gestión y empresas — para revisar de un vistazo.</div>\n          <div class="table-scroll">\n          <table><thead><tr><th>Asesor</th><th>Zona</th><th>Estado</th><th>Meses activo</th><th>Ventas ejecutadas</th><th>% Cumpl. ventas</th><th>% Cumpl. gestión</th><th>Empresas gestionadas</th><th>Empresas faltantes</th></tr></thead><tbody id="tblResumenConsolidado"></tbody></table>\n          </div>\n        </div>\n      </div>\n    </section>\n\n    '
new_html_7c = 'grid" id="resumenKpis"></div>\n      <div class="section-desc" style="margin-top:10px;">Mismos indicadores, pero del mes en curso.</div>\n      <div class="kpi-grid" id="resumenKpisMes"></div>\n      <div class="grid2">\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Ventas ejecutadas — tendencia marzo a la fecha</span></div>\n          <div class="chart-box"><canvas id="chResumenTendencia"></canvas></div>\n        </div>\n        <div class="card">\n          <div class="card-title"><span><span class="dot"></span>Empresas por estado de contacto</span></div>\n          <div class="chart-box"><canvas id="chResumenEmpresas"></canvas></div>\n        </div>\n      </div>\n\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Gestión integral — por mes</span></div>\n        <div class="table-scroll"><table id="tblResumenGestionMes"></table></div>\n        <div class="chart-box" style="height:220px;margin-top:12px;"><canvas id="chResumenGestionMesTendencia"></canvas></div>\n      </div>\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Medios de contacto — por mes</span></div>\n        <div class="table-scroll"><table id="tblResumenMediosMes"></table></div>\n        <div class="chart-box" style="height:220px;margin-top:12px;"><canvas id="chResumenMediosMesTendencia"></canvas></div>\n      </div>\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Ventas por servicio — cantidad por mes</span></div>\n        <div class="table-scroll"><table id="tblResumenVentasServMes"></table></div>\n        <div class="chart-box" style="height:220px;margin-top:12px;"><canvas id="chResumenVentasServMesTendencia"></canvas></div>\n      </div>\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Empresas atendidas por tamaño — por mes</span></div>\n        <div class="table-scroll"><table id="tblResumenEmpresasTamMes"></table></div>\n        <div class="chart-box" style="height:220px;margin-top:12px;"><canvas id="chResumenEmpresasTamMesTendencia"></canvas></div>\n      </div>\n\n      <div class="card">\n        <div class="card-title"><span><span class="dot"></span>Ejecución de Ventas (por asesor)</span></div>\n        <div class="section-desc">Ordenado de mayor a menor por el Total (acumulado + mes en curso). % Participación = qué parte del acumulado vendido por el equipo aporta cada asesor.</div>\n        <div class="table-scroll">\n        <table><thead><tr><th>Asesor</th><th>Desde</th><th>Hasta</th><th>Meses activo</th><th>Ejecutado</th><th>% Participación</th><th>Ejecución mes en curso</th><th>Total</th></tr></thead><tbody id="tblResumenVentasEjecucion"></tbody></table>\n        </div>\n      </div>\n    </section>\n\n    '
assert old_html_7c in final_html, "Paso 7c: no se encontro el bloque HTML de Resumen (Gerencial)"
assert final_html.count(old_html_7c)==1
final_html = final_html.replace(old_html_7c, new_html_7c)

anchor_7c = "// ================= GESTIÓN ================="
assert final_html.count(anchor_7c)==1
final_html = final_html.replace(anchor_7c, '// ---- Mes en curso (31-ago-2026, a pedido de Luis): tarjetas espejo de resumenKpis + 4 cuadros mes-a-mes ----\nconst ymActual = ventasD.meses_order[ventasD.meses_order.length-1];\nconst mesLabelActual = ventasD.mes_labels[ymActual] || ymActual;\nconst rawGesAllTop = DATA.gestiones.raw_gestiones || [];\nconst rawGesMesTop = rawGesAllTop.filter(r=>(r.fecha||\'\').slice(0,7)===ymActual);\nconst mesActualTendEq = ventasD.tendencia[ventasD.tendencia.length-1];\nconst pctMesEquipo = mesActualTendEq.meta>0 ? (mesActualTendEq.ventas/mesActualTendEq.meta*100) : 0;\n\nfunction countTagPeriodo(rows, tag){\n  return rows.filter(r=>(r.gestion||\'\').split(\'/\').some(p=>p.trim()===tag)).length;\n}\nconst MEDIO_MAP_TOP = {\'Llamada\':\'Llamadas\',\'WhatsApp\':\'WhatsApp\',\'Correo electrónico\':\'Correos\',\'Visita presencial\':\'Visitas presenciales\',\'Reunión virtual\':\'Reunión virtual\'};\n// % ejecución del mes (Gestión): solo Promoción + Mantenimiento + Medios de contacto -- son los\n// unicos frentes con fuente mensual real (raw_gestiones/medio). Ventas (Cotizaciones, Ordenes de\n// compra, etc.) es conteo de negociaciones de Bitrix sin desglose mensual disponible en DATA, asi\n// que se deja fuera de este promedio (su $ si tiene mes en curso propio, en la tarjeta de al lado).\nconst NOMBRE_TAG_GESTION = {\n  \'Actualización de base de datos\': \'Actualización de datos\',\n  \'Visita por primera vez\': \'Empresa contactada por primera vez\',\n  \'Presentación de portafolio\': \'Presentación de Portafolio\',\n};\nlet sumaPctGesMes = 0, nIndGesMes = 0;\ncontract.categories.forEach(cat=>{\n  if (cat.name===\'Ventas\') return;\n  cat.indicators.forEach(ind=>{\n    if (ind.pending) return;\n    const metaMes = (ind.meta_6m||0)/6;\n    if (!(metaMes>0)) return;\n    let realMes;\n    if (cat.name===\'Medios de contacto\') realMes = rawGesMesTop.filter(r=>MEDIO_MAP_TOP[r.medio]===ind.name).length;\n    else realMes = countTagPeriodo(rawGesMesTop, NOMBRE_TAG_GESTION[ind.name] || ind.name);\n    sumaPctGesMes += Math.min(realMes/metaMes, 1.5);\n    nIndGesMes++;\n  });\n});\nconst pctGestionMes = nIndGesMes ? (sumaPctGesMes/nIndGesMes*100) : 0;\nconst nitEmpMesSet = new Set(rawGesMesTop.map(r=>r.nit).filter(Boolean));\nconst nitEmpPrimeraVezMesSet = new Set(rawGesMesTop.filter(r=>(r.gestion||\'\').split(\'/\').some(p=>p.trim()===\'Empresa contactada por primera vez\')).map(r=>r.nit).filter(Boolean));\n\ndocument.getElementById(\'resumenKpisMes\').innerHTML = `\n  <div class="kpi"><div class="kv">${pctGestionMes.toFixed(0)}%</div><div class="kl">Ejecución del mes (Gestión)</div></div>\n  <div class="kpi acc"><div class="kv">${fmtM(mesActualTendEq.ventas)}</div><div class="kl">Ventas ejecutadas (${mesLabelActual})</div></div>\n  <div class="kpi"><div class="kv">${fmtM(mesActualTendEq.meta)}</div><div class="kl">Meta del mes (${pctMesEquipo.toFixed(0)}% ejecutado)</div></div>\n  <div class="kpi"><div class="kv">${fmtN(nitEmpMesSet.size)}</div><div class="kl">Empresas atendidas este mes</div></div>\n  <div class="kpi"><div class="kv">${fmtN(nitEmpPrimeraVezMesSet.size)}</div><div class="kl">Contactadas por primera vez este mes</div></div>\n`;\n\n// ---- Helper generico: tabla categoria x mes con totales + grafico de linea ----\nfunction renderMatrizMes(elId, chartId, rows, months, monthLabels, dataFn, chartLabel, color){\n  const totalPorMes = {}; months.forEach(m=>totalPorMes[m]=0);\n  let totalGeneral = 0;\n  const bodyRows = rows.map(r=>{\n    let rowTotal = 0;\n    const tds = months.map(m=>{\n      const v = dataFn(r.key, m) || 0;\n      totalPorMes[m] += v; rowTotal += v;\n      return `<td>${v.toLocaleString(\'es-CO\')}</td>`;\n    }).join(\'\');\n    totalGeneral += rowTotal;\n    return `<tr><td>${r.label}</td>${tds}<td style="font-weight:700;">${rowTotal.toLocaleString(\'es-CO\')}</td></tr>`;\n  }).join(\'\');\n  const totalRow = `<tr style="font-weight:700;background:#f4f6f5;"><td>Total</td>${months.map(m=>`<td>${totalPorMes[m].toLocaleString(\'es-CO\')}</td>`).join(\'\')}<td>${totalGeneral.toLocaleString(\'es-CO\')}</td></tr>`;\n  const thead = `<thead><tr><th>Categoría</th>${months.map(m=>`<th>${monthLabels[m]||m}</th>`).join(\'\')}<th>Total</th></tr></thead>`;\n  const elTable = document.getElementById(elId);\n  if (elTable) elTable.innerHTML = thead + \'<tbody>\' + bodyRows + totalRow + \'</tbody>\';\n  const elChart = document.getElementById(chartId);\n  if (elChart) new Chart(elChart, {\n    type:\'line\',\n    data:{ labels: months.map(m=>monthLabels[m]||m), datasets:[{ label: chartLabel, data: months.map(m=>totalPorMes[m]||0), borderColor:color, backgroundColor:color+\'33\', fill:true, tension:0.3, pointRadius:3 }] },\n    options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}}\n  });\n  return totalPorMes;\n}\n\n// 1) Gestión integral por mes (mismas 10 categorías del informe mensual)\nconst CATS_GESTION_ROWS = [\n  [\'Asesorías generales\',\'Asesorías generales\'],\n  [\'Presentación de Portafolio\',\'Presentación de portafolio\'],\n  [\'Empresa contactada por primera vez\',\'Empresa contactada por primera vez\'],\n  [\'Actualización de datos\',\'Actualización de datos\'],\n  [\'Actividades de mantenimiento\',\'Actividades de mantenimiento\'],\n  [\'Gestión fallida\',\'Gestión fallida\'],\n  [\'Seguimiento ventas\',\'Seguimiento de ventas\'],\n  [\'Acompañamiento servicio postventa\',\'Acompañamiento postventa\'],\n  [\'Feria de servicios\',\'Feria de servicios\'],\n  [\'Empresa ilocalizable\',\'Empresa ilocalizable\'],\n].map(([key,label])=>({key,label}));\nfunction countTagMonth(rows, tag, ym){\n  return rows.filter(r=>(r.fecha||\'\').slice(0,7)===ym && (r.gestion||\'\').split(\'/\').some(p=>p.trim()===tag)).length;\n}\nrenderMatrizMes(\'tblResumenGestionMes\',\'chResumenGestionMesTendencia\', CATS_GESTION_ROWS, ventasD.meses_order, ventasD.mes_labels,\n  (key,ym)=>countTagMonth(rawGesAllTop, key, ym), \'Gestiones\', \'#00685E\');\n\n// 2) Medios de contacto por mes\nconst MEDIOS_ROWS = [\n  [\'Llamada\',\'Llamadas\'],[\'WhatsApp\',\'WhatsApp\'],[\'Correo electrónico\',\'Correos\'],\n  [\'Visita presencial\',\'Visitas presenciales\'],[\'Reunión virtual\',\'Reunión virtual\'],\n].map(([key,label])=>({key,label}));\nrenderMatrizMes(\'tblResumenMediosMes\',\'chResumenMediosMesTendencia\', MEDIOS_ROWS, ventasD.meses_order, ventasD.mes_labels,\n  (key,ym)=>rawGesAllTop.filter(r=>(r.fecha||\'\').slice(0,7)===ym && r.medio===key).length, \'Medios de contacto\', \'#FF6900\');\n\n// 3) Ventas por servicio por mes (catalogo oficial, cantidad de ventas) -- se llena mas abajo,\n// despues de que el Paso de Ventas calcule ventasD.transacciones[].servicio_oficial.\nwindow.__renderVentasServicioMes = function(){\n  const catalogo = Object.keys(IMPUESTO_OFICIAL).map(k=>({key:k,label:k}));\n  renderMatrizMes(\'tblResumenVentasServMes\',\'chResumenVentasServMesTendencia\', catalogo, ventasD.meses_order, ventasD.mes_labels,\n    (key,ym)=>ventasD.transacciones.filter(t=>t.ym===ym && t.servicio_oficial===key).length, \'Ventas\', \'#1F2A44\');\n};\n\n// 4) Empresas atendidas por tamaño por mes\nconst empTamByNitTop = {};\n(DATA.empresas_full||[]).forEach(e=>{ empTamByNitTop[e.nit] = e.tam || \'Sin dato\'; });\nconst TAM_ROWS = [[\'Grande\',\'Grande\'],[\'Mediana\',\'Mediana\'],[\'Pequeña\',\'Pequeña\'],[\'Micro\',\'Micro\']].map(([key,label])=>({key,label}));\nrenderMatrizMes(\'tblResumenEmpresasTamMes\',\'chResumenEmpresasTamMesTendencia\', TAM_ROWS, ventasD.meses_order, ventasD.mes_labels,\n  (tam,ym)=>{\n    const nits = new Set();\n    rawGesAllTop.forEach(r=>{ if((r.fecha||\'\').slice(0,7)===ym && r.nit && empTamByNitTop[r.nit]===tam) nits.add(r.nit); });\n    return nits.size;\n  }, \'Empresas atendidas\', \'#8850A0\');\n\n' + '\n' + anchor_7c)

old_js_7c = '// ================= RESUMEN: cumplimiento vs metas contractuales =================\n(function(){\n  const rowsVen = advisorsFull.map(a=>{\n    const r = ventasRankByName[a.name];\n    if (!r || !r.meta_acumulada_5m) return null;\n    const pct = r.meta_acumulada_5m>0 ? (r.total_acumulado/r.meta_acumulada_5m*100) : null;\n    return {name:a.name, meses:a.meses_activos||r.meses_activos, real:r.total_acumulado, meta:r.meta_acumulada_5m, pct};\n  }).filter(Boolean).sort((a,b)=>(b.pct||0)-(a.pct||0));\n  document.getElementById(\'tblResumenVentasMeta\').innerHTML = rowsVen.map(r=>{\n    const cls = r.pct!=null? statusClass(r.pct):\'na\';\n    return `<tr><td>${r.name}</td><td>${r.meses}</td><td>${fmt(r.real)}</td><td>${fmt(r.meta)}</td><td><span class="badge ${cls||\'ok\'}">${r.pct!=null?r.pct.toFixed(0)+\'%\':\'—\'}</span></td></tr>`;\n  }).join(\'\');\n\n  const rowsGes = advisorsFull.slice().sort((a,b)=>b.accumulated.global_pct-a.accumulated.global_pct).map(a=>{\n    const pct = a.accumulated.global_pct*100;\n    return {name:a.name, meses:a.meses_activos, pct, active:a.active};\n  });\n  document.getElementById(\'tblResumenGestionMeta\').innerHTML = rowsGes.map(r=>{\n    const cls = statusClass(r.pct);\n    return `<tr><td>${r.name}</td><td>${r.meses}</td><td><span class="badge ${cls||\'ok\'}">${r.pct.toFixed(0)}%</span></td><td><span class="badge ${r.active===false?\'off\':\'on\'}">${r.active===false?\'Inactivo\':\'Activo\'}</span></td></tr>`;\n  }).join(\'\');\n\n  const rowsCons = advisorsFull.map(a=>{\n    const rv = ventasRankByName[a.name] || {};\n    const pctVentas = rv.meta_acumulada_5m ? (rv.total_acumulado/rv.meta_acumulada_5m*100) : null;\n    const pctGestion = a.accumulated.global_pct*100;\n    return {\n      name: a.name, zona: rv.zona || \'—\', active: a.active, meses: a.meses_activos,\n      ventas: rv.total_acumulado||0, pctVentas, pctGestion,\n      gestionadas: a.empresas_gestionadas_contrato||0, faltantes: a.empresas_faltantes_contrato||0,\n    };\n  }).sort((a,b)=>(b.pctGestion||0)-(a.pctGestion||0));\n  document.getElementById(\'tblResumenConsolidado\').innerHTML = rowsCons.map(r=>{\n    const clsV = r.pctVentas!=null? statusClass(r.pctVentas):\'na\';\n    const clsG = statusClass(r.pctGestion);\n    return `<tr><td>${r.name}</td><td>${r.zona}</td><td><span class="badge ${r.active===false?\'off\':\'on\'}">${r.active===false?\'Inactivo\':\'Activo\'}</span></td><td>${r.meses}</td><td>${fmt(r.ventas)}</td><td><span class="badge ${clsV||\'ok\'}">${r.pctVentas!=null?r.pctVentas.toFixed(0)+\'%\':\'—\'}</span></td><td><span class="badge ${clsG||\'ok\'}">${r.pctGestion.toFixed(0)}%</span></td><td>${r.gestionadas}</td><td>${r.faltantes}</td></tr>`;\n  }).join(\'\');\n})();\n\n\n'
new_js_7c = '(function(){\n  const gesLblVen = DATA.gestiones.month_labels || {};\n  const mesActualVenByAsesor = {};\n  ventasD.transacciones.forEach(t=>{\n    if (t.ym===ymActual) mesActualVenByAsesor[t.asesor] = (mesActualVenByAsesor[t.asesor]||0) + t.valor;\n  });\n  const rowsVen = advisorsFull.map(a=>{\n    const r = ventasRankByName[a.name];\n    const mesesN = a.meses_activos || (r ? r.meses_activos : 0) || 0;\n    const mesActualVal = mesActualVenByAsesor[a.name] || 0;\n    if (!mesesN && !mesActualVal) return null;\n    const real = r ? (r.total_acumulado||0) : 0;\n    const mesesArr = (a.active_months||[]).slice().sort();\n    const desde = mesesArr.length? (gesLblVen[mesesArr[0]] || mesesArr[0]) : \'—\';\n    const hasta = mesesArr.length? (gesLblVen[mesesArr[mesesArr.length-1]] || mesesArr[mesesArr.length-1]) : \'—\';\n    return {name:a.name, mesesN, desde, hasta, real, mesActualVal};\n  }).filter(Boolean);\n  // Asesores con venta este mes que no aparecen en advisorsFull (p.ej. salieron sin que Luis lo\n  // haya confirmado aun) igual deben ver su valor de mes en curso -- no depende del roster.\n  const yaIncluidosVen = new Set(rowsVen.map(r=>r.name));\n  Object.keys(mesActualVenByAsesor).forEach(name=>{\n    if (yaIncluidosVen.has(name)) return;\n    rowsVen.push({name, mesesN:0, desde:\'—\', hasta:\'—\', real:0, mesActualVal: mesActualVenByAsesor[name]});\n  });\n  rowsVen.forEach(r=>{ r.total = r.real + r.mesActualVal; });\n  rowsVen.sort((a,b)=>b.total-a.total);\n  const totalVenEj = rowsVen.reduce((s,r)=>s+r.real,0);\n  const totalMesVenEj = rowsVen.reduce((s,r)=>s+r.mesActualVal,0);\n  const totalGralVenEj = rowsVen.reduce((s,r)=>s+r.total,0);\n  const tblVenEj = document.getElementById(\'tblResumenVentasEjecucion\');\n  if (tblVenEj) tblVenEj.innerHTML = rowsVen.map(r=>{\n    const part = totalVenEj>0 ? (r.real/totalVenEj*100) : 0;\n    return `<tr><td>${r.name}</td><td>${r.desde}</td><td>${r.hasta}</td><td>${r.mesesN}</td><td>${fmt(r.real)}</td><td>${part.toFixed(1)}%</td><td>${fmt(r.mesActualVal)}</td><td style="font-weight:700;">${fmt(r.total)}</td></tr>`;\n  }).join(\'\') + `<tr style="font-weight:700;background:#f4f6f5;"><td colspan="4">Total</td><td>${fmt(totalVenEj)}</td><td>100%</td><td>${fmt(totalMesVenEj)}</td><td>${fmt(totalGralVenEj)}</td></tr>`;\n\n\n})();\n\n\n'
assert old_js_7c in final_html, "Paso 7c: no se encontro el IIFE viejo de Resumen (Gerencial)"
assert final_html.count(old_js_7c)==1
final_html = final_html.replace(old_js_7c, new_js_7c)

anchor_serv_7c = "populateSelect('fVenServicio', [...new Set(ventasD.transacciones.map(r=>r.servicio_oficial))].sort());"
if anchor_serv_7c in final_html and final_html.count(anchor_serv_7c)==1:
    final_html = final_html.replace(anchor_serv_7c, anchor_serv_7c + "\n if (window.__renderVentasServicioMes) window.__renderVentasServicioMes();")

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 7c aplicado: Resumen Gerencial -- mismo diseno unificado que Operativo (tarjetas mes en curso + 4 cuadros mes-a-mes + tabla asesores +2 columnas).")


# ---------- 7d. Gestión (Equipo): merge tarjetas + reordenar zonas (31-ago-2026, a pedido de Luis, "Hoja de gestion.docx") ----------
# A diferencia de Operativo: Gerencial no tiene tarjeta "Medios de contacto" propia (nunca la tuvo),
# asi que no se agrega tarjeta "Indicadores de gestion" aca por ahora (falta esa infraestructura) --
# decision de alcance comunicada a Luis. El boton "Exportar a Excel" de Detalle de gestiones SI se
# mantiene en Gerencial (Luis: "para el dashboard gerencial si dejemoslo").
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_merge_7d = '''document.getElementById('gestionKpis').insertAdjacentHTML('beforeend', `
  <div class="kpi ok"><div class="kv">${bestInd? (bestInd[1].pctSum/bestInd[1].pctN*100).toFixed(0)+'%':'—'}</div><div class="kl">Mejor indicador: ${bestInd?bestInd[0]:'—'}</div></div>
  <div class="kpi"><div class="kv">${indRanked.length?indRanked[0][0]:'—'}</div><div class="kl">Actividad más realizada (${indRanked.length?fmtN(indRanked[0][1].real):0})</div></div>
  <div class="kpi"><div class="kv">${fmtN(cotizTotal.real)}/${fmtN(cotizTotal.meta)}</div><div class="kl">Cotizaciones (equipo)</div></div>
  <div class="kpi"><div class="kv">${fmtN(ocTotal.real)}/${fmtN(ocTotal.meta)}</div><div class="kl">Órdenes de compra (equipo)</div></div>
`);'''
new_merge_7d = '''document.getElementById('gestionKpis').insertAdjacentHTML('beforeend', `
  <div class="kpi ok"><div class="kv">${bestInd?bestInd[0]:'—'}</div><div class="kl">Mejor indicador (${bestInd?(bestInd[1].pctSum/bestInd[1].pctN*100).toFixed(0)+'%':'—'}) · más realizada (${indRanked.length?fmtN(indRanked[0][1].real):0})</div></div>
  <div class="kpi"><div class="kv">${fmtN(cotizTotal.real)}/${fmtN(cotizTotal.meta)}</div><div class="kl">Cotizaciones (equipo)</div></div>
  <div class="kpi"><div class="kv">${fmtN(ocTotal.real)}/${fmtN(ocTotal.meta)}</div><div class="kl">Órdenes de compra (equipo)</div></div>
`);'''
assert old_merge_7d in final_html, "Paso 7d: no se encontro el bloque de tarjetas Mejor indicador/Actividad mas realizada (Gerencial)"
final_html = final_html.replace(old_merge_7d, new_merge_7d)

old_zona_7d = '''document.getElementById('gestionZonaCards').innerHTML = Object.entries(zonaGestion).map(([z,inds])=>{
  const pcts = Object.values(inds).filter(v=>v.meta>0).map(v=>Math.min(v.real/v.meta,1.5));
  const pctAvg = pcts.length? (pcts.reduce((s,p)=>s+p,0)/pcts.length*100) : 0;
  const nAse = zonaAdvisorSet[z] ? zonaAdvisorSet[z].size : 0;
  return `<div class="zona-card"><h3>${z}</h3><div class="zona-row">Asesores <b>${nAse}</b></div><div class="zona-row">Cumplimiento promedio <b>${pctAvg.toFixed(0)}%</b></div></div>`;
}).join('');'''
new_zona_7d = '''const ZONA_ORDEN = ['Santa Marta','Call Center','IFT','Ciénaga','Fundación'];
document.getElementById('gestionZonaCards').innerHTML = Object.entries(zonaGestion)
  .sort((a,b)=>ZONA_ORDEN.indexOf(a[0])-ZONA_ORDEN.indexOf(b[0]))
  .map(([z,inds])=>{
  const pcts = Object.values(inds).filter(v=>v.meta>0).map(v=>Math.min(v.real/v.meta,1.5));
  const pctAvg = pcts.length? (pcts.reduce((s,p)=>s+p,0)/pcts.length*100) : 0;
  const nAse = zonaAdvisorSet[z] ? zonaAdvisorSet[z].size : 0;
  return `<div class="zona-card"><h3>${z}</h3><div class="zona-row">Asesores <b>${nAse}</b></div><div class="zona-row">Cumplimiento promedio <b>${pctAvg.toFixed(0)}%</b></div></div>`;
}).join('');'''
assert old_zona_7d in final_html, "Paso 7d: no se encontro el bloque de gestionZonaCards (Gerencial)"
final_html = final_html.replace(old_zona_7d, new_zona_7d)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 7d aplicado: Gestion (Equipo) Gerencial -- tarjetas 'Mejor indicador'+'Actividad mas realizada' fusionadas y zonas reordenadas (Santa Marta/Call Center/IFT/Cienaga/Fundacion). Boton Exportar a Excel se mantiene sin cambios.")


# ---------- 7e. Gestion (Equipo) Gerencial: agregar tarjetas 'Indicadores de gestion' + 'Medios de contacto' real vs. meta (31-ago-2026, a pedido de Luis) ----------
# Gerencial nunca tuvo estas 2 tarjetas (a diferencia de Operativo); se agregan ahora con el
# mismo criterio (real acumulado del contrato vs. meta_6m x elapsed_fraction).
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_card_7e = '''        <div class="grid2">
          <div class="card">
            <div class="card-title"><span><span class="dot"></span>Medios de contacto utilizados (equipo, volumen)</span></div>
            <div class="chart-box sm"><canvas id="chGestionMedios"></canvas></div>
          </div>
        </div>
      </div>'''
new_card_7e = '''        <div class="grid2">
          <div class="card">
            <div class="card-title"><span><span class="dot"></span>Medios de contacto utilizados (equipo, volumen)</span></div>
            <div class="chart-box sm"><canvas id="chGestionMedios"></canvas></div>
          </div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Indicadores de gestión — real vs. meta (equipo, acumulado del contrato)</span></div>
          <div class="kpi-grid" id="gestionIndicadoresMetas"></div>
        </div>
        <div class="card">
          <div class="card-title"><span><span class="dot"></span>Medios de contacto — real vs. meta (equipo, acumulado del contrato)</span></div>
          <div class="kpi-grid" id="gestionMediosMetas"></div>
        </div>
      </div>'''
assert old_card_7e in final_html, "Paso 7e: no se encontro el bloque HTML de Medios de contacto (Gerencial)"
final_html = final_html.replace(old_card_7e, new_card_7e)

old_js_7e = '''new Chart(document.getElementById('chGestionMedios'),{
  type:'bar', data:{ labels: medioSorted.map(x=>x[0]), datasets:[{label:'Gestiones', data: medioSorted.map(x=>x[1]), backgroundColor:'#2E75B6aa'}] },
  options:{indexAxis:'y', responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}}
});'''
new_js_7e = '''new Chart(document.getElementById('chGestionMedios'),{
  type:'bar', data:{ labels: medioSorted.map(x=>x[0]), datasets:[{label:'Gestiones', data: medioSorted.map(x=>x[1]), backgroundColor:'#2E75B6aa'}] },
  options:{indexAxis:'y', responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}}
});

// ---- Indicadores de gestión / Medios de contacto real vs. meta (equipo, acumulado del contrato) ----
// (31-ago-2026, a pedido de Luis: mismo par de tarjetas que ya existe en Operativo)
document.getElementById('gestionIndicadoresMetas').innerHTML = contract.categories
  .filter(c=>c.name==='Promoción' || c.name==='Mantenimiento')
  .flatMap(c=>c.indicators).filter(i=>!i.pending).map(i=>{
    const expected = i.meta_6m*contract.elapsed_fraction;
    const pct = expected>0 ? Math.min(i.real/expected,1.5)*100 : 0;
    const cls = statusClass(pct);
    return `<div class="kpi ${cls}"><div class="kv">${pct.toFixed(0)}%</div><div class="kl">${i.name}</div><div class="ks">${fmtN(i.real)} / ${fmtN(i.meta_6m)} meta contrato</div></div>`;
  }).join('');

document.getElementById('gestionMediosMetas').innerHTML = (contract.categories.find(c=>c.name==='Medios de contacto')?.indicators||[])
  .filter(i=>!i.pending).map(i=>{
    const expected = i.meta_6m*contract.elapsed_fraction;
    const pct = expected>0 ? Math.min(i.real/expected,1.5)*100 : 0;
    const cls = statusClass(pct);
    return `<div class="kpi ${cls}"><div class="kv">${pct.toFixed(0)}%</div><div class="kl">${i.name}</div><div class="ks">${fmtN(i.real)} / ${fmtN(i.meta_6m)} meta contrato</div></div>`;
  }).join('');'''
assert old_js_7e in final_html, "Paso 7e: no se encontro el bloque JS de chGestionMedios (Gerencial)"
final_html = final_html.replace(old_js_7e, new_js_7e)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 7e aplicado: Gestion (Equipo) Gerencial -- +tarjetas 'Indicadores de gestion' (Promocion+Mantenimiento) y 'Medios de contacto' real vs. meta (equipo, acumulado del contrato), igual que Operativo.")

# --- Paso 8. Ventas: doble linea de meta en "Tendencia mensual (segun filtro)" (1-sep-2026, a
# pedido de Luis). Igual que Operativo (linea 1 = meta individual del asesor/zona filtrada,
# reutilizando la misma tasa mensual real validada en Resumen), MAS una segunda linea, solo en
# Gerencial, con la meta CONTRACTUAL real (mas aterrizada -- ejemplo de Luis: "10 millones por
# asesor" vs. los 21-32M de meta individual interna). Esa 2da linea se deriva de
# meta_contractual_mensual (el monto fijo del contrato, ~98.3M/mes = contrato anual / 12, no
# depende de cuantos asesores hay) repartido proporcionalmente entre los asesores activos del
# filtro vigente -- se calcula asi (en vez de usar el campo precalculado
# meta_contractual_zona_mensual) porque ese campo esta incompleto/desactualizado (le faltan
# Call Center e IFT), y este reparto dinamico siempre suma correctamente al total del contrato.
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_tendmeta_ger = '''  // ---- Tendencia mensual (dentro del filtro) ----
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
new_tendmeta_ger = '''  // ---- Tendencia mensual (dentro del filtro) ----
  // NOTA (3-sep-2026, a pedido de Luis): Gerencial muestra UNICAMENTE la meta contractual
  // real (los 590M del contrato, prorateados a 98.3M/mes), nunca las metas individuales
  // internas del equipo (que suman mas, ~352M/mes, y son solo referencia interna de
  // Operativo). Antes esta grafica tenia una 2da linea de "meta individual" que en algunos
  // filtros de asesor/zona mostraba una cifra mas alta que el contrato -- se quito.
  const tendData = ventasD.meses_order.map(ym=>porMes[ym]||0);
  const tendLabels = ventasD.meses_order.map(ym=>ventasD.mes_labels[ym]);
  const aseSelVen = document.getElementById('fVenAsesor').value;
  const zonaSelVen = document.getElementById('fVenZona').value;
  const totalActivosVen = activeAdvisors.length || 1;
  const metaContractualPorAsesor = ventasD.meta_contractual_mensual / totalActivosVen;
  let metaContractualLinea = ventasD.meta_contractual_mensual;
  let metaContractualLabel = 'Meta contractual real (equipo, 590M/6 meses)';
  if (aseSelVen){
    metaContractualLinea = metaContractualPorAsesor;
    metaContractualLabel = `Meta contractual real, prorrateada (${aseSelVen})`;
  } else if (zonaSelVen){
    const activosZonaVen = activeAdvisors.filter(a=>a.current_profile===zonaSelVen);
    metaContractualLinea = metaContractualPorAsesor * activosZonaVen.length;
    metaContractualLabel = `Meta contractual real, prorrateada (${zonaSelVen})`;
  }
  const tendMetaContractual = ventasD.meses_order.map(()=>metaContractualLinea);
  if (!chVentasTendencia){
    chVentasTendencia = new Chart(document.getElementById('chVentasTendencia'),{
      type:'bar', data:{ labels: tendLabels,
        datasets:[
          {label:'Ejecutado (filtro)', data: tendData, backgroundColor:'#00685Eaa', borderRadius:5},
          {label:metaContractualLabel, data: tendMetaContractual, type:'line', borderColor:'#1F2A44', borderDash:[6,4], pointRadius:2, fill:false},
        ]}, options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}, scales:{y:{ticks:{callback:v=>(v/1000000)+'M'}}}}
    });
  } else {
    chVentasTendencia.data.datasets[0].data = tendData;
    chVentasTendencia.data.datasets[1].data = tendMetaContractual;
    chVentasTendencia.data.datasets[1].label = metaContractualLabel;
    chVentasTendencia.update();
  }'''
assert old_tendmeta_ger in final_html, "Paso 8: no se encontro el bloque JS de Tendencia mensual (Ventas, Gerencial)"
final_html = final_html.replace(old_tendmeta_ger, new_tendmeta_ger)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)

# ---------- 9. Resumen: "Ventas por servicio" -- misma tarjeta que en Operativo (2-sep-2026,
# a pedido de Luis, tambien aqui en Gerencial). Barras horizontales rankeadas por valor, estilo
# Tablero TV (renderVentasPorServicio): nombre + barra proporcional + $ + cantidad + % del total,
# top 8 + "Otros", sobre el contrato completo a la fecha. ----------
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_card_9 = '''      <div class="card">
        <div class="card-title"><span><span class="dot"></span>Ventas por servicio — cantidad por mes</span></div>
        <div class="table-scroll"><table id="tblResumenVentasServMes"></table></div>
        <div class="chart-box" style="height:220px;margin-top:12px;"><canvas id="chResumenVentasServMesTendencia"></canvas></div>
      </div>'''
new_card_9 = '''      <div class="card">
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
assert old_card_9 in final_html, "Paso 9: no se encontro la tarjeta 'Ventas por servicio -- cantidad por mes' (Gerencial)"
final_html = final_html.replace(old_card_9, new_card_9)

old_fn_9 = '''window.__renderVentasServicioMes = function(){
  const catalogo = Object.keys(IMPUESTO_OFICIAL).map(k=>({key:k,label:k}));
  renderMatrizMes(\'tblResumenVentasServMes\',\'chResumenVentasServMesTendencia\', catalogo, ventasD.meses_order, ventasD.mes_labels,
    (key,ym)=>ventasD.transacciones.filter(t=>t.ym===ym && t.servicio_oficial===key).length, \'Ventas\', \'#1F2A44\');
};'''
new_fn_9 = '''const SVC_COLORS_RESUMEN = [\'#5b8def\',\'#3ecf8e\',\'#f5a524\',\'#ee6c6c\',\'#a78bfa\',\'#22c1c3\',\'#f472b6\',\'#c084fc\',\'#94a3b8\'];
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
assert old_fn_9 in final_html, "Paso 9: no se encontro window.__renderVentasServicioMes (Gerencial)"
final_html = final_html.replace(old_fn_9, new_fn_9)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 9 aplicado (Gerencial): Resumen -- 'Ventas por servicio' ahora es la misma grafica de barras horizontales del Tablero TV (top 8 + Otros, $ y % del total), sobre el contrato completo a la fecha.")

# ---------- 10. Resumen: tabla "Ejecucion de Ventas (por asesor)" -- misma correccion que
# Operativo (2-sep-2026, a pedido de Luis: "los cambios de ultimos cambios se tenian que aplicar
# al gerencial y al operativo... lo unico que no debe quedar en el gerencial [es la meta +25%]").
# Quita % Participacion, ordena por Ejecucion mes en curso, renombra Ejecutado. ----------
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_desc_10 = '''<div class="section-desc">Ordenado de mayor a menor por el Total (acumulado + mes en curso). % Participación = qué parte del acumulado vendido por el equipo aporta cada asesor.</div>
        <div class="table-scroll">
        <table><thead><tr><th>Asesor</th><th>Desde</th><th>Hasta</th><th>Meses activo</th><th>Ejecutado</th><th>% Participación</th><th>Ejecución mes en curso</th><th>Total</th></tr></thead><tbody id="tblResumenVentasEjecucion"></tbody></table>'''
new_desc_10 = '''<div class="section-desc">Ordenado de mayor a menor por la Ejecución mes en curso.</div>
        <div class="table-scroll">
        <table><thead><tr><th>Asesor</th><th>Desde</th><th>Hasta</th><th>Meses activo</th><th>Ejecutado meses anteriores</th><th>Ejecución mes en curso</th><th>Total</th></tr></thead><tbody id="tblResumenVentasEjecucion"></tbody></table>'''
assert old_desc_10 in final_html, "Paso 10: no se encontro el bloque HTML de la tabla Ejecucion de Ventas (Gerencial)"
final_html = final_html.replace(old_desc_10, new_desc_10)

old_sort_10 = '''rowsVen.sort((a,b)=>b.total-a.total);'''
new_sort_10 = '''rowsVen.sort((a,b)=>b.mesActualVal-a.mesActualVal);'''
assert old_sort_10 in final_html, "Paso 10: no se encontro el sort de rowsVen (Gerencial)"
final_html = final_html.replace(old_sort_10, new_sort_10)

old_render_10 = '''if (tblVenEj) tblVenEj.innerHTML = rowsVen.map(r=>{
    const part = totalVenEj>0 ? (r.real/totalVenEj*100) : 0;
    return `<tr><td>${r.name}</td><td>${r.desde}</td><td>${r.hasta}</td><td>${r.mesesN}</td><td>${fmt(r.real)}</td><td>${part.toFixed(1)}%</td><td>${fmt(r.mesActualVal)}</td><td style="font-weight:700;">${fmt(r.total)}</td></tr>`;
  }).join('') + `<tr style="font-weight:700;background:#f4f6f5;"><td colspan="4">Total</td><td>${fmt(totalVenEj)}</td><td>100%</td><td>${fmt(totalMesVenEj)}</td><td>${fmt(totalGralVenEj)}</td></tr>`;'''
new_render_10 = '''if (tblVenEj) tblVenEj.innerHTML = rowsVen.map(r=>{
    return `<tr><td>${r.name}</td><td>${r.desde}</td><td>${r.hasta}</td><td>${r.mesesN}</td><td>${fmt(r.real)}</td><td>${fmt(r.mesActualVal)}</td><td style="font-weight:700;">${fmt(r.total)}</td></tr>`;
  }).join('') + `<tr style="font-weight:700;background:#f4f6f5;"><td colspan="4">Total</td><td>${fmt(totalVenEj)}</td><td>${fmt(totalMesVenEj)}</td><td>${fmt(totalGralVenEj)}</td></tr>`;'''
assert old_render_10 in final_html, "Paso 10: no se encontro el render de filas de rowsVen (Gerencial)"
final_html = final_html.replace(old_render_10, new_render_10)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 10 aplicado (Gerencial): Resumen -- tabla 'Ejecucion de Ventas (por asesor)' sin columna % Participacion, ordenada por Ejecucion mes en curso, 'Ejecutado' renombrado a 'Ejecutado meses anteriores'.")

# ---------- 11. Empresas: filtro por fecha "contactadas hasta" (2-sep-2026, tambien en
# Gerencial). Misma logica que Operativo, adaptada al set de filtros de Gerencial (sin el
# filtro "Estado" unificado que solo existe en Operativo). ----------
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_filters_11 = '''      <div class="filters">
        <div class="filter-group"><label>Buscar</label><input type="text" id="fEmpBuscar" placeholder="Nombre o NIT..."></div>
        <div class="filter-group"><label>Estado de contacto</label><select id="fEmpPer"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Tamaño</label><select id="fEmpTam"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Estado afiliación</label><select id="fEmpEst"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Asesor</label><select id="fEmpAse"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Equipo/Zona</label><select id="fEmpEq"><option value="">Todas</option></select></div>
        <div class="filter-group"><label>Dificultad</label><select id="fEmpDif"><option value="">Todas</option></select></div>
        <button class="filter-clear" id="btnClearEmp">Limpiar</button>
      </div>'''
new_filters_11 = '''      <div class="filters">
        <div class="filter-group"><label>Buscar</label><input type="text" id="fEmpBuscar" placeholder="Nombre o NIT..."></div>
        <div class="filter-group"><label>Estado de contacto</label><select id="fEmpPer"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Tamaño</label><select id="fEmpTam"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Estado afiliación</label><select id="fEmpEst"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Asesor</label><select id="fEmpAse"><option value="">Todos</option></select></div>
        <div class="filter-group"><label>Equipo/Zona</label><select id="fEmpEq"><option value="">Todas</option></select></div>
        <div class="filter-group"><label>Dificultad</label><select id="fEmpDif"><option value="">Todas</option></select></div>
        <div class="filter-group"><label>Contactadas hasta (contrato actual)</label><input type="date" id="fEmpHastaFecha"></div>
        <button class="filter-clear" id="btnClearEmp">Limpiar</button>
      </div>
      <div class="section-desc" id="empFechaCorteNota" style="display:none;"></div>'''
assert old_filters_11 in final_html, "Paso 11: no se encontro el panel de filtros de Empresas (Gerencial)"
final_html = final_html.replace(old_filters_11, new_filters_11)

old_gef_11 = '''function getEmpresasFiltered(){
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
new_gef_11 = '''const primerContactoPorNit = {};
(DATA.gestiones.raw_gestiones||[]).forEach(r=>{
  if (!r.nit || !r.fecha) return;
  if (!primerContactoPorNit[r.nit] || r.fecha < primerContactoPorNit[r.nit]) primerContactoPorNit[r.nit] = r.fecha;
});
function perAsOfFecha(r, hastaFecha){
  if (r.per !== 'Contactada - contrato actual' && r.per !== 'No contactada') return r.per;
  const pc = primerContactoPorNit[r.nit];
  return (pc && pc <= hastaFecha) ? 'Contactada - contrato actual' : 'No contactada';
}
function getEmpresasFiltered(){
  const q = document.getElementById('fEmpBuscar').value.trim().toLowerCase();
  const per = document.getElementById('fEmpPer').value;
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
  if (tam) rows = rows.filter(r=>r.tam===tam);
  if (est) rows = rows.filter(r=>r.est===est);
  if (ase) rows = rows.filter(r=>r.ase===ase);
  if (eq) rows = rows.filter(r=>r.eq===eq);
  if (dif) rows = rows.filter(r=>r.dif===dif);
  return rows;
}'''
assert old_gef_11 in final_html, "Paso 11: no se encontro getEmpresasFiltered (Gerencial)"
final_html = final_html.replace(old_gef_11, new_gef_11)

old_listeners_11 = '''['fEmpBuscar'].forEach(id=>document.getElementById(id).addEventListener('input', renderEmpresasAll));
['fEmpPer','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif'].forEach(id=>document.getElementById(id).addEventListener('change', renderEmpresasAll));
document.getElementById('btnClearEmp').addEventListener('click',()=>{
  ['fEmpBuscar','fEmpPer','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif'].forEach(id=>document.getElementById(id).value='');
  renderEmpresasAll();
});'''
new_listeners_11 = '''function actualizarNotaFechaCorte(){
  const el = document.getElementById('empFechaCorteNota');
  const v = document.getElementById('fEmpHastaFecha').value;
  if (!el) return;
  if (v){ el.style.display='block'; el.textContent = `Mostrando el estado de contacto (contrato actual) tal como estaba el ${v} — no el estado de hoy.`; }
  else { el.style.display='none'; el.textContent=''; }
}
['fEmpBuscar'].forEach(id=>document.getElementById(id).addEventListener('input', renderEmpresasAll));
['fEmpPer','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif'].forEach(id=>document.getElementById(id).addEventListener('change', renderEmpresasAll));
document.getElementById('fEmpHastaFecha').addEventListener('change', ()=>{ actualizarNotaFechaCorte(); renderEmpresasAll(); });
document.getElementById('btnClearEmp').addEventListener('click',()=>{
  ['fEmpBuscar','fEmpPer','fEmpTam','fEmpEst','fEmpAse','fEmpEq','fEmpDif','fEmpHastaFecha'].forEach(id=>document.getElementById(id).value='');
  actualizarNotaFechaCorte();
  renderEmpresasAll();
});'''
assert old_listeners_11 in final_html, "Paso 11: no se encontro el bloque de listeners de Empresas (Gerencial)"
final_html = final_html.replace(old_listeners_11, new_listeners_11)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 11 aplicado (Gerencial): Empresas -- nuevo filtro de fecha 'Contactadas hasta (contrato actual)', igual que en Operativo.")

# ---------- 12. Resumen: linea comparativa 2025 en "Gestion integral" y "Empresas atendidas"
# (tambien en Gerencial, misma fuente y mismo criterio que Operativo -- ver Paso 24 de
# build_operativo.py para el detalle completo de por que "Medios de contacto" no lleva 2025). ----------
with open(OUT, encoding='utf-8') as f:
    final_html = f.read()

old_helper_12 = '''function renderMatrizMes(elId, chartId, rows, months, monthLabels, dataFn, chartLabel, color){
  const totalPorMes = {}; months.forEach(m=>totalPorMes[m]=0);
  let totalGeneral = 0;
  const bodyRows = rows.map(r=>{
    let rowTotal = 0;
    const tds = months.map(m=>{
      const v = dataFn(r.key, m) || 0;
      totalPorMes[m] += v; rowTotal += v;
      return `<td>${v.toLocaleString('es-CO')}</td>`;
    }).join('');
    totalGeneral += rowTotal;
    return `<tr><td>${r.label}</td>${tds}<td style="font-weight:700;">${rowTotal.toLocaleString('es-CO')}</td></tr>`;
  }).join('');
  const totalRow = `<tr style="font-weight:700;background:#f4f6f5;"><td>Total</td>${months.map(m=>`<td>${totalPorMes[m].toLocaleString('es-CO')}</td>`).join('')}<td>${totalGeneral.toLocaleString('es-CO')}</td></tr>`;
  const thead = `<thead><tr><th>Categoría</th>${months.map(m=>`<th>${monthLabels[m]||m}</th>`).join('')}<th>Total</th></tr></thead>`;
  const elTable = document.getElementById(elId);
  if (elTable) elTable.innerHTML = thead + '<tbody>' + bodyRows + totalRow + '</tbody>';
  const elChart = document.getElementById(chartId);
  if (elChart) new Chart(elChart, {
    type:'line',
    data:{ labels: months.map(m=>monthLabels[m]||m), datasets:[{ label: chartLabel, data: months.map(m=>totalPorMes[m]||0), borderColor:color, backgroundColor:color+'33', fill:true, tension:0.3, pointRadius:3 }] },
    options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}}
  });
  return totalPorMes;
}'''
new_helper_12 = '''function renderMatrizMes(elId, chartId, rows, months, monthLabels, dataFn, chartLabel, color, serie2025){
  const totalPorMes = {}; months.forEach(m=>totalPorMes[m]=0);
  let totalGeneral = 0;
  const bodyRows = rows.map(r=>{
    let rowTotal = 0;
    const tds = months.map(m=>{
      const v = dataFn(r.key, m) || 0;
      totalPorMes[m] += v; rowTotal += v;
      return `<td>${v.toLocaleString('es-CO')}</td>`;
    }).join('');
    totalGeneral += rowTotal;
    return `<tr><td>${r.label}</td>${tds}<td style="font-weight:700;">${rowTotal.toLocaleString('es-CO')}</td></tr>`;
  }).join('');
  const totalRow = `<tr style="font-weight:700;background:#f4f6f5;"><td>Total</td>${months.map(m=>`<td>${totalPorMes[m].toLocaleString('es-CO')}</td>`).join('')}<td>${totalGeneral.toLocaleString('es-CO')}</td></tr>`;
  const thead = `<thead><tr><th>Categoría</th>${months.map(m=>`<th>${monthLabels[m]||m}</th>`).join('')}<th>Total</th></tr></thead>`;
  const elTable = document.getElementById(elId);
  if (elTable) elTable.innerHTML = thead + '<tbody>' + bodyRows + totalRow + '</tbody>';
  const elChart = document.getElementById(chartId);
  if (elChart){
    const datasets = [{ label: chartLabel, data: months.map(m=>totalPorMes[m]||0), borderColor:color, backgroundColor:color+'33', fill:true, tension:0.3, pointRadius:3 }];
    if (serie2025) datasets.push({ label: chartLabel + ' 2025 (contrato anterior)', data: serie2025, borderColor:'#8a8f98', backgroundColor:'transparent', borderDash:[6,4], fill:false, tension:0.3, pointRadius:3, spanGaps:false });
    new Chart(elChart, {
      type:'line',
      data:{ labels: months.map(m=>monthLabels[m]||m), datasets },
      options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display: !!serie2025}}}
    });
  }
  return totalPorMes;
}

const GESTIONES_2025_POR_MES = {'2026-03':null, '2026-04':2462, '2026-05':1258, '2026-06':650, '2026-07':1243, '2026-08':1024};
const EMPRESAS_GESTIONADAS_2025_POR_MES = {'2026-03':null, '2026-04':1106, '2026-05':664, '2026-06':363, '2026-07':511, '2026-08':552};'''
assert old_helper_12 in final_html, "Paso 12: no se encontro renderMatrizMes (Gerencial)"
final_html = final_html.replace(old_helper_12, new_helper_12)

old_call_gestion_12 = '''renderMatrizMes('tblResumenGestionMes','chResumenGestionMesTendencia', CATS_GESTION_ROWS, ventasD.meses_order, ventasD.mes_labels,
  (key,ym)=>countTagMonth(rawGesAllTop, key, ym), 'Gestiones', '#00685E');'''
new_call_gestion_12 = '''renderMatrizMes('tblResumenGestionMes','chResumenGestionMesTendencia', CATS_GESTION_ROWS, ventasD.meses_order, ventasD.mes_labels,
  (key,ym)=>countTagMonth(rawGesAllTop, key, ym), 'Gestiones', '#00685E', ventasD.meses_order.map(ym=>GESTIONES_2025_POR_MES[ym]));'''
assert old_call_gestion_12 in final_html, "Paso 12: no se encontro la llamada de renderMatrizMes para Gestion integral (Gerencial)"
final_html = final_html.replace(old_call_gestion_12, new_call_gestion_12)

old_call_emp_12 = '''renderMatrizMes('tblResumenEmpresasTamMes','chResumenEmpresasTamMesTendencia', TAM_ROWS, ventasD.meses_order, ventasD.mes_labels,
  (tam,ym)=>{
    const nits = new Set();
    rawGesAllTop.forEach(r=>{ if((r.fecha||'').slice(0,7)===ym && r.nit && empTamByNitTop[r.nit]===tam) nits.add(r.nit); });
    return nits.size;
  }, 'Empresas atendidas', '#8850A0');'''
new_call_emp_12 = '''renderMatrizMes('tblResumenEmpresasTamMes','chResumenEmpresasTamMesTendencia', TAM_ROWS, ventasD.meses_order, ventasD.mes_labels,
  (tam,ym)=>{
    const nits = new Set();
    rawGesAllTop.forEach(r=>{ if((r.fecha||'').slice(0,7)===ym && r.nit && empTamByNitTop[r.nit]===tam) nits.add(r.nit); });
    return nits.size;
  }, 'Empresas atendidas', '#8850A0', ventasD.meses_order.map(ym=>EMPRESAS_GESTIONADAS_2025_POR_MES[ym]));'''
assert old_call_emp_12 in final_html, "Paso 12: no se encontro la llamada de renderMatrizMes para Empresas atendidas (Gerencial)"
final_html = final_html.replace(old_call_emp_12, new_call_emp_12)

# ---------- 13. Resumen KPI: comparativo empresas gestionadas contrato anterior vs actual ----------
# 3-sep-2026, corregido a pedido de Luis: el numero del informe de avance (5121 acumulado,
# 3863 a la misma altura) SUMA gestiones repetidas mes a mes (una empresa visitada en 4 meses
# distintos cuenta 4 veces) y ademas no distinguia gestion comercial real de negociaciones de
# venta individual (una empresa cuyo unico "contacto" fue que le vendimos una poliza a un
# empleado no deberia contar como "empresa gestionada"). Se reemplaza por el conteo real,
# bajado directo de Bitrix (reporte "Gestiones CER", Pipeline = "Promocion, Mantenimiento y
# Afiliaciones" UNICAMENTE -- se excluyen a proposito los pipelines VENTA INDIVIDUAL y VENTA
# EMPRESARIAL), de NITs de empresa DISTINTOS (no repetidos) con al menos una gestion registrada:
#   - Abril-Septiembre 2025 (misma altura del calendario que el contrato actual): 1.435 empresas
#   - Abril 2025 - Enero 2026 (contrato anterior completo): 1.506 empresas
old_resumen_kpis_13 = '''  <div class="kpi"><div class="kv">${DATA.empresas_agg.per_counts['Contactada - contrato actual']||0}</div><div class="kl">Empresas contactadas (contrato actual)</div></div>
  <div class="kpi bad"><div class="kv">${DATA.empresas_agg.per_counts['No contactada']||0}</div><div class="kl">Empresas no contactadas</div></div>
`;'''
new_resumen_kpis_13 = '''  <div class="kpi"><div class="kv">${DATA.empresas_agg.per_counts['Contactada - contrato actual']||0}</div><div class="kl">Empresas contactadas (contrato actual)</div></div>
  <div class="kpi bad"><div class="kv">${DATA.empresas_agg.per_counts['No contactada']||0}</div><div class="kl">Empresas no contactadas</div></div>
  <div class="kpi"><div class="kv">${DATA.empresas_agg.per_counts['Contactada - contrato actual']||0}</div><div class="kl">Empresas distintas gestionadas -- contrato actual (a la fecha)</div></div>
  <div class="kpi"><div class="kv">1.435</div><div class="kl">Empresas distintas gestionadas -- contrato anterior (misma altura del calendario, abr-sep 2025, Bitrix)</div></div>
  <div class="kpi"><div class="kv">1.506</div><div class="kl">Empresas distintas gestionadas -- contrato anterior (total, abr2025-ene2026, Bitrix)</div></div>
`;'''
assert old_resumen_kpis_13 in final_html, "Paso 13: no se encontro el cierre del bloque resumenKpis (Gerencial)"
final_html = final_html.replace(old_resumen_kpis_13, new_resumen_kpis_13)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final_html)
print("Paso 12 aplicado (Gerencial): Resumen -- 'Gestion integral' y 'Empresas atendidas por tamaño' con linea 2025 comparativa, igual que Operativo.")
print("Paso 8 aplicado: Ventas (Gerencial) -- 'Tendencia mensual' ahora con 2 lineas de meta: la individual del asesor/zona filtrada (igual que Operativo) y la meta contractual real (mas aterrizada, prorrateada segun el filtro vigente).")
print("Paso 13 aplicado (Gerencial): Resumen -- 3 KPIs nuevos de comparativo empresas gestionadas (contrato actual a la fecha / contrato anterior a la misma altura / contrato anterior total).")
