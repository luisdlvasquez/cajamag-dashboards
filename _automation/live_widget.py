"""
Retirado (25-ago-2026, a pedido de Luis): el widget flotante 'EN VIVO' en la
esquina inferior derecha se quita de los 3 dashboards. Esa información (ventas
del día, más reciente primero) ahora vive integrada en la pantalla "Ventas del
día" del Tablero TV (ver renderVentasDelDia en TV_Master_DATA.html), que ya
consulta bitrix_eventos ordenado por creado_en.desc (de la última venta
registrada a la primera).

Este script se conserva solo para LIMPIAR el marcador del widget de archivos
que todavia lo tengan incrustado de corridas anteriores (build_operativo.py /
build_gerencial.py / pipeline_master.py regeneran el archivo desde cero, así
que ya no hace falta re-inyectar nada aquí). inject() ahora es idempotente en
el sentido opuesto: si encuentra el marcador antiguo lo borra; si no lo
encuentra, no toca el archivo.

Uso manual:
    python3 live_widget.py Dashboard_Operativo_CER.html Dashboard_Gerencial_CER.html Tablero_TV_Asesores_CER.html
"""
import sys

MARKER_START = "<!-- CER-LIVE-FEED-WIDGET v2 -->"
MARKER_END = "<!-- /CER-LIVE-FEED-WIDGET v2 -->"

SUPA_URL = "https://nzmnzmnozbeqttofbmlf.supabase.co"
SUPA_ANON = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im56bW56"
             "bW5vemJlcXR0b2ZibWxmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk2NTAzMjQsImV4cCI6MjA5NTIy"
             "NjMyNH0.r3hrXsazoJK_xUWTsskEgjQ40Xhg60_0YaGvWs1VXP8")

WIDGET_HTML = """<!-- CER-LIVE-FEED-WIDGET v2 -->
<div id="cer-live-feed" style="position:fixed;right:16px;bottom:16px;z-index:9998;width:300px;max-width:88vw;font-family:'Montserrat',system-ui,sans-serif;">
  <div style="background:#fff;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.18);border:1px solid #e2e5e8;overflow:hidden;">
    <div id="cer-live-feed-header" style="background:#00685E;color:#fff;padding:8px 12px;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:space-between;cursor:pointer;">
      <span style="display:flex;align-items:center;gap:6px;"><span style="width:8px;height:8px;border-radius:50%;background:#4CD964;display:inline-block;animation:cerpulse 1.5s infinite;"></span>EN VIVO — Ventas cerradas hoy</span>
      <span id="cer-live-feed-toggle">▾</span>
    </div>
    <div id="cer-live-feed-list" style="max-height:220px;overflow-y:auto;font-size:12px;">
      <div style="padding:10px 12px;color:#98a2ac;">Cargando…</div>
    </div>
  </div>
</div>
<style>@keyframes cerpulse{0%{opacity:1}50%{opacity:.3}100%{opacity:1}}</style>
<script>
(function(){
  var SUPA_URL = '__SUPA_URL__';
  var SUPA_KEY = '__SUPA_ANON__';
  function fmtMonto(n){ if(n==null) return ''; return '$'+Math.round(n).toLocaleString('es-CO'); }
  function fmtHora(iso){ try{ var d=new Date(iso); return d.toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'}); }catch(e){return '';} }
  function load(){
    fetch(SUPA_URL+'/rest/v1/bitrix_eventos?estado_auditoria=eq.aprobado&evento=neq.backfill_historico&order=creado_en.desc&limit=15', {
      headers: { apikey: SUPA_KEY, Authorization: 'Bearer '+SUPA_KEY }
    }).then(function(r){ return r.json(); }).then(function(rows){
      var el = document.getElementById('cer-live-feed-list');
      if(!el) return;
      if(!Array.isArray(rows) || !rows.length){ el.innerHTML = '<div style="padding:10px 12px;color:#98a2ac;">Sin ventas confirmadas todavia.</div>'; return; }
      el.innerHTML = rows.map(function(r){
        return '<div style="padding:8px 12px;border-top:1px solid #eef0f2;">'
          + '<div style="font-weight:700;color:#004d45;">'+(r.titulo||('Negocio '+r.deal_id))+'</div>'
          + '<div style="color:#5B6770;">'+(r.asesor||'—')+' · '+fmtMonto(r.monto)+' · '+fmtHora(r.creado_en)+'</div>'
          + '</div>';
      }).join('');
    }).catch(function(e){ console.error('live feed error', e); });
  }
  var collapsed = false;
  function wire(){
    var hdr = document.getElementById('cer-live-feed-header');
    var list = document.getElementById('cer-live-feed-list');
    var tgl = document.getElementById('cer-live-feed-toggle');
    if(hdr){
      hdr.addEventListener('click', function(){
        collapsed = !collapsed;
        list.style.display = collapsed ? 'none' : '';
        tgl.textContent = collapsed ? '▸' : '▾';
      });
    }
  }
  if(document.readyState === 'loading'){ document.addEventListener('DOMContentLoaded', wire); } else { wire(); }
  load();
  setInterval(load, 30000);
})();
</script>
<!-- /CER-LIVE-FEED-WIDGET v2 -->"""

WIDGET_HTML = WIDGET_HTML.replace("__SUPA_URL__", SUPA_URL).replace("__SUPA_ANON__", SUPA_ANON)


def inject(path):
    """Ya NO agrega el widget flotante (retirado). Solo limpia el marcador
    si el archivo lo trae de una version anterior."""
    with open(path, encoding="utf-8") as f:
        html = f.read()

    if MARKER_START in html and MARKER_END in html:
        i = html.index(MARKER_START)
        j = html.index(MARKER_END) + len(MARKER_END)
        html = html[:i] + html[j:]
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print("widget en vivo (flotante) retirado de", path)
    else:
        print("sin widget flotante que retirar en", path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 live_widget.py archivo1.html [archivo2.html ...]")
        sys.exit(1)
    for p in sys.argv[1:]:
        inject(p)
