"""
recompute_tv_empresas.py — Re-deriva TODOS los agregados de empresas por
tamaño del Tablero TV (TV_Master_DATA.html) a partir de empresas_full ya
corregido en Dashboard_Master_DATA.html (ver etl_empresas.py).

Se usa cuando cambia la clasificación de tamaño (empresas_full/tam) sin que
haya un repull nuevo de Bitrix (ventas/gestiones no cambian, así que no
hace falta correr el pipeline completo, solo re-derivar lo que depende de
'tam'):
    - TVDATA['empresas']['detalle_por_asesor'][*].asignadas_by_tam / .../
      atendidas_mes_by_tam / ilocalizadas_by_tam / gestiones_by_tam
    - TVDATA['empresas']['detalle_por_asesor'][*].iloc_mes (ilocalizables
      encontradas en gestiones del mes en curso, con nombres)
    - TVDATA['empresas']['detalle_por_asesor'][*].cadencia (cumplimiento de
      la directriz de frecuencia de visitas por tamaño, ver CADENCIA_DIAS)
    - TVDATA['empresas']['detalle_por_asesor'][*].cadencia_pendientes (nombres
      de las empresas de cada tamaño que NO cumplen la directriz a hoy, para
      la pantalla de "Empresas por Atender — detalle")
    - TVDATA['empresas']['contactadas_por_mes'][YM] / contactadas_por_mes_total[YM]

Replica exactamente la lógica que ya vive en pipeline_master.py (sección
"Detalle de empresas por asesor") para que ambos scripts nunca diverjan.
"""
import glob, os, sys, json, re
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict

_env_base = os.environ.get("PIPELINE_BASE_DIR")
if _env_base:
    BASE = _env_base
else:
    _candidates = glob.glob("/sessions/*/mnt/Trabajando Juntos")
    if not _candidates:
        print("ERROR: no se encontro la carpeta 'Trabajando Juntos' montada bajo /sessions/*/mnt/")
        sys.exit(1)
    _mnt = os.path.dirname(_candidates[0])
    BASE = f"{_candidates[0]}/CAJAMAG/02_DASHBOARDS"
AUTO = f"{BASE}/_automation"
MASTER = f"{AUTO}/Dashboard_Master_DATA.html"
TV_MASTER = f"{AUTO}/TV_Master_DATA.html"

def effective_today(real_today=None):
    """Misma regla que pipeline_master.py (actualizada 17-sep-2026 a pedido
    de Luis): del dia 1 al 7 (inclusive) del mes nuevo, el tablero sigue
    tratando el mes ANTERIOR como 'mes en curso'; desde el dia 8 usa el mes
    real."""
    t = real_today or date.today()
    if t.day <= 7:
        first_of_month = t.replace(day=1)
        return first_of_month - timedelta(days=1)
    return t


REAL_TODAY = date.today()
TODAY = effective_today(REAL_TODAY)
YM = TODAY.strftime('%Y-%m')

TAM_RANK = {'Grande': 0, 'Mediana': 1, 'Pequeña': 2, 'Micro': 3}

# Directriz de frecuencia de visitas de Cajamag por tamaño de empresa
# (version corregida por Luis Lobera, 25-ago-2026):
#   Grande  : minimo 1 gestion EN EL MES en curso
#   Mediana : minimo 1 gestion EN EL MES en curso
#   Pequeña : minimo 1 gestion cada 60 dias (a partir de la ultima gestion)
#   Micro   : minimo 1 gestion durante TODO el contrato (no es periodico,
#             basta con que se haya gestionado alguna vez en el contrato)
# El denominador ("asignadas") es SIEMPRE el total de empresas de ese
# tamaño asignadas al asesor (todas, sin importar si ya estan en gestion o
# no) — no solo las que ya estaban marcadas 'Contactada - contrato actual'.
CADENCIA_MENSUAL = {'Grande', 'Mediana'}   # exigen gestion este mes
CADENCIA_DIAS = {'Pequeña': 60}             # exigen gestion en los ultimos N dias
CADENCIA_CONTRATO = {'Micro'}                # exigen al menos 1 gestion en todo el contrato


def norm_tam(t):
    t = t or 'Sin dato'
    return 'Micro' if t == 'Sin dato' else t


def find_blob_bounds(html, key_pattern):
    """Encuentra los limites {..} de un valor JSON dentro del HTML, contando
    llaves/corchetes con cuidado de comillas escapadas."""
    m = re.search(key_pattern, html)
    assert m, f"no se encontro {key_pattern}"
    start = m.end() - 1
    depth = 0
    in_str = False
    esc = False
    i = start
    while i < len(html):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c in '{[':
                depth += 1
            elif c in '}]':
                depth -= 1
                if depth == 0:
                    return start, i + 1
        i += 1
    raise AssertionError("no se encontro el cierre del blob")


def main():
    master_html = open(MASTER, encoding='utf-8').read()
    d_start = master_html.index('const DATA = ') + len('const DATA = ')
    d_end = master_html.index('function fmt(n)')
    data = json.loads(master_html[d_start:d_end].rstrip()[:-1])

    ef = data['empresas_full']
    raw_all = data['gestiones']['raw_gestiones']
    af = data['gestiones']['advisors_full']
    month_raw = [r for r in raw_all if r['fecha'].startswith(YM)]

    tam_by_nit_global = {e['nit']: norm_tam(e.get('tam')) for e in ef if e.get('nit')}

    # ---- fecha de ultima gestion por NIT (para la cadencia) ----
    ultima_gestion_por_nit = {}
    for r in raw_all:
        nit = r.get('nit')
        if not nit:
            continue
        if nit not in ultima_gestion_por_nit or r['fecha'] > ultima_gestion_por_nit[nit]:
            ultima_gestion_por_nit[nit] = r['fecha']
    fue_por_nit = {e['nit']: e.get('fue') for e in ef if e.get('nit')}
    nits_gestionadas_alguna_vez = set(ultima_gestion_por_nit.keys())
    TAM_ORDER_ALL = ['Grande', 'Mediana', 'Pequeña', 'Micro']

    def dias_desde(fecha_str):
        if not fecha_str:
            return None
        try:
            d = datetime.strptime(fecha_str[:10], '%Y-%m-%d').date()
        except ValueError:
            return None
        # Fecha real (no la TODAY 'efectiva' congelada por la regla de cierre
        # de mes): la cadencia siempre debe reflejar el tiempo real transcurrido.
        return (REAL_TODAY - d).days

    detalle_por_asesor = {}
    for a in af:
        name = a['name']
        rows = [e for e in ef if e.get('ase') == name]
        asignadas_by_tam = Counter()
        gestionadas_by_tam = Counter()
        sin_gestion_by_tam = Counter()
        pendientes_by_tam = Counter()
        potenciales = []
        for e in rows:
            tam = norm_tam(e.get('tam'))
            asignadas_by_tam[tam] += 1
            per = e.get('per')
            if per == 'Contactada - contrato actual':
                gestionadas_by_tam[tam] += 1
            elif per == 'No contactada':
                sin_gestion_by_tam[tam] += 1
                potenciales.append(e)
            elif per == 'Contactada - solo contrato anterior':
                pendientes_by_tam[tam] += 1
        potenciales.sort(key=lambda e: TAM_RANK.get(norm_tam(e.get('tam')), 3))
        top3 = potenciales[:3]

        my_gestion_rows = [r for r in raw_all if r['asesor'] == name and r.get('nit')]
        gestiones_by_tam = Counter()
        for r in my_gestion_rows:
            gestiones_by_tam[tam_by_nit_global.get(r['nit'], 'Micro')] += 1

        ilocalizadas_rows = [e for e in rows if e.get('iloc')]
        ilocalizadas_by_tam = Counter(norm_tam(e.get('tam')) for e in ilocalizadas_rows)

        my_month_rows = [r for r in month_raw if r.get('asesor') == name]
        my_month_nits = set(r['nit'] for r in my_month_rows if r.get('nit'))
        atendidas_mes_by_tam = Counter(tam_by_nit_global.get(n, 'Micro') for n in my_month_nits)
        por_dia_asesor = defaultdict(set)
        for r in my_month_rows:
            if r.get('nit'):
                por_dia_asesor[r['fecha']].add(r['nit'])
        dia_vals = [len(s) for s in por_dia_asesor.values()]
        dia_stats_asesor = {
            'promedio': round(sum(dia_vals) / len(dia_vals), 1) if dia_vals else 0,
            'minimo': min(dia_vals) if dia_vals else 0,
            'maximo': max(dia_vals) if dia_vals else 0,
            'dias_con_gestion': len(dia_vals),
        } if dia_vals else None

        # Mismo ritmo diario pero SOLO contando visitas presenciales (medio
        # == 'Visita presencial'), por empresa distinta visitada ese dia.
        my_month_visitas = [r for r in my_month_rows if (r.get('medio') or '').strip() == 'Visita presencial']
        por_dia_visitas = defaultdict(set)
        for r in my_month_visitas:
            if r.get('nit'):
                por_dia_visitas[r['fecha']].add(r['nit'])
        dia_vals_visitas = [len(s) for s in por_dia_visitas.values()]
        dia_stats_visitas = {
            'promedio': round(sum(dia_vals_visitas) / len(dia_vals_visitas), 1) if dia_vals_visitas else 0,
            'minimo': min(dia_vals_visitas) if dia_vals_visitas else 0,
            'maximo': max(dia_vals_visitas) if dia_vals_visitas else 0,
            'dias_con_gestion': len(dia_vals_visitas),
        } if dia_vals_visitas else None

        # Ilocalizables encontradas EN GESTIONES DE ESTE MES (no el estado
        # historico del contrato completo) — con nombres de empresa.
        iloc_mes_rows = [r for r in my_month_rows if 'ilocaliz' in (r.get('gestion') or '').lower()]
        iloc_mes_nombres = sorted(set(r.get('empresa') for r in iloc_mes_rows if r.get('empresa')))
        iloc_mes = {'total': len(iloc_mes_nombres), 'nombres': iloc_mes_nombres}

        # Cadencia de visitas: se evalua contra TODAS las empresas asignadas
        # a este asesor de ese tamaño (no solo las ya marcadas 'en gestion'),
        # con una regla distinta segun tamaño:
        #   Grande/Mediana : necesitan >=1 gestion EN EL MES en curso
        #   Pequeña        : necesitan la ultima gestion dentro de N dias
        #   Micro          : necesitan >=1 gestion en TODO el contrato
        cadencia = {}
        cadencia_pendientes = {}
        for tam in TAM_ORDER_ALL:
            asignadas_tam = [e for e in rows if norm_tam(e.get('tam')) == tam]
            cumple_n = 0
            pendientes_nombres = []
            for e in asignadas_tam:
                nit = e.get('nit')
                if tam in CADENCIA_MENSUAL:
                    ok = bool(nit and nit in my_month_nits)
                elif tam in CADENCIA_DIAS:
                    d = dias_desde(ultima_gestion_por_nit.get(nit) or e.get('fue'))
                    ok = d is not None and d <= CADENCIA_DIAS[tam]
                else:  # CADENCIA_CONTRATO (Micro): basta 1 gestion en todo el contrato
                    ok = bool(nit and nit in nits_gestionadas_alguna_vez)
                if ok:
                    cumple_n += 1
                else:
                    pendientes_nombres.append(e.get('nom') or 'Sin nombre')
            cadencia[tam] = {
                'asignadas': len(asignadas_tam),
                'cumple': cumple_n,
                'atrasada': len(asignadas_tam) - cumple_n,
            }
            cadencia_pendientes[tam] = sorted(pendientes_nombres)

        detalle_por_asesor[name] = {
            'asignadas_by_tam': dict(asignadas_by_tam),
            'gestionadas_by_tam': dict(gestionadas_by_tam),
            'sin_gestion_by_tam': dict(sin_gestion_by_tam),
            'pendientes_by_tam': dict(pendientes_by_tam),
            'gestiones_by_tam': dict(gestiones_by_tam),
            'atendidas_mes_by_tam': dict(atendidas_mes_by_tam),
            'atendidas_mes_total': len(my_month_nits),
            'ilocalizadas_by_tam': dict(ilocalizadas_by_tam),
            'ilocalizadas_total': len(ilocalizadas_rows),
            'dia_stats': dia_stats_asesor,
            'dia_stats_visitas': dia_stats_visitas,
            'total_gestiones': len(my_gestion_rows),
            'total_asignadas': len(rows),
            'top3_potenciales': [{'nombre': e.get('nom'), 'tam': norm_tam(e.get('tam')), 'municipio': e.get('mun')} for e in top3],
            'iloc_mes': iloc_mes,
            'cadencia': cadencia,
            'cadencia_pendientes': cadencia_pendientes,
        }

    tam_by_nit = {e['nit']: (e['tam'] or 'Sin dato') for e in ef if e.get('nit')}
    month_nits = set(r['nit'] for r in month_raw if r.get('nit'))
    tam_counter = Counter()
    for n in month_nits:
        tam = tam_by_nit.get(n, 'Sin dato')
        if tam == 'Sin dato':
            tam = 'Micro'
        tam_counter[tam] += 1

    # ---- Escribir en TV_Master_DATA.html ----
    tv_html = open(TV_MASTER, encoding='utf-8').read()

    s, e = find_blob_bounds(tv_html, r'window\.TVDATA\s*=\s*(\{)')
    tvdata = json.loads(tv_html[s:e])

    tvdata['empresas']['detalle_por_asesor'] = detalle_por_asesor
    tvdata['empresas']['contactadas_por_mes'][YM] = dict(tam_counter)
    tvdata['empresas']['contactadas_por_mes_total'][YM] = sum(tam_counter.values())

    new_blob = json.dumps(tvdata, ensure_ascii=False, separators=(',', ':'))
    tv_html2 = tv_html[:s] + new_blob + tv_html[e:]
    open(TV_MASTER, 'w', encoding='utf-8').write(tv_html2)
    print(f"TV_Master_DATA.html actualizado. {len(detalle_por_asesor)} asesores recalculados.")
    print("contactadas_por_mes[%s]: %s" % (YM, dict(tam_counter)))


if __name__ == '__main__':
    main()
