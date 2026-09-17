"""
Pipeline maestro CAJAMAG — actualiza Dashboard_Master_DATA.html y TV_Master_DATA.html
con datos frescos de Bitrix (mes en curso, del día 1 hasta hoy), y regenera los 3
archivos publicables (Dashboard_Operativo_CER.html, Dashboard_Gerencial_CER.html,
Tablero_TV_Asesores_CER.html) + un zip listo para desplegar en Netlify.

USO:
  1. Descargar de Bitrix (categoría Negociaciones, filtro "Fase ganada" + "Fecha de
     facturación" en rango 01/MM/AAAA-hoy, exportar "todos los campos" + SKU):
       - VENTA INDIVIDUAL   (category 2)  -> guardar como individual.xls en DL
       - VENTA EMPRESARIAL  (category 1)  -> guardar como empresarial.xls en DL
       - IFT                (category 4, etapa "CERRADO MATRICULARO") -> ift.xls en DL
     Descargar también el reporte guardado "Gestiones CER" (Analítica > Informes >
     Reportes del personal), con "Pipeline de la negociación" = "Todos" (CORREGIDO
     1-sep-2026: el filtro viejo lo restringia solo a "Promoción, Mantenimiento y
     Afiliaciones", lo que excluia silenciosamente toda la actividad registrada en
     los otros 17 pipelines de Bitrix -- causa raiz del subconteo reportado por
     Luis, ej. Bienvenida Lopez Hurtado con 16 visitas en el dashboard vs 24-25
     reales) y "Fecha y hora evento" en rango 01/MM/AAAA-hoy, exportado a Excel
     (debe incluir la columna "Etapa de la negociación") -> guardar como
     gestiones.xls en DL.
  2. Ejecutar: python pipeline_master.py
  3. Verificar con los scripts de test (test_operativo2.js, test_gerencial.js,
     test_tv_aug.js adaptados) antes de avisar al usuario.
  4. El zip queda en OUT_DIR listo para arrastrar a Netlify Drop (el deploy final
     sigue siendo manual hasta que se configure un token de Netlify API).

Todo esto está pensado para poder ejecutarse de nuevo sin duplicar datos: SIEMPRE
reemplaza por completo el mes en curso (nunca lo suma incrementalmente), y no toca
los meses ya cerrados ni el archivo de empresas (empresas_full/tam), que se congela
hasta que alguien lo actualice explícitamente vía etl_empresas.py.

REGLA DE ETAPA (confirmada por Luis, 1-sep-2026): de las gestiones descargadas
(ahora con Pipeline="Todos"), solo se cuentan como "ya sucedidas" las que estan en
etapa EJECUCIÓN EVENTO, CERRADO GANADO o CERRADO PERDIDO (cierre real, ganado o
perdido). Se excluyen PLANIFICACIÓN EVENTO, EVENTO APLAZADO, NEGOCIACIÓN, y
cualquier otra etapa de "todavia no paso" (ASIGNACIÓN, CALIFICACIÓN, NUEVA
OPORTUNIDAD, SEGUIMIENTO, IDENTIFICACIÓN EMPRESA, AFINACIÓN/DESARROLLO/PROPUESTA
ENVIADA, etc.) por logica explicita de Luis. Este cambio aplica SOLO hacia
adelante (mes en curso en cada corrida): los meses ya cerrados/entregados antes de
esta fecha NO se recalculan retroactivamente.
"""
import glob, os, sys
import json, pickle, re, unicodedata
import pandas as pd
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict

# Localiza la carpeta de trabajo. Prioridad:
#   1) PIPELINE_BASE_DIR (usado por GitHub Actions: el propio checkout del repo)
#   2) auto-deteccion de "Trabajando Juntos" montada en Cowork (/sessions/<id>/mnt/)
_env_base = os.environ.get("PIPELINE_BASE_DIR")
if _env_base:
    BASE = _env_base
    AUTO = f"{BASE}/_automation"
    DL = os.environ.get("BITRIX_EXPORT_DIR", f"{BASE}/_bitrix_export/")
    OUT_DIR = os.environ.get("PIPELINE_OUT_DIR", f"{BASE}/_out")
    os.makedirs(OUT_DIR, exist_ok=True)
else:
    _candidates = glob.glob("/sessions/*/mnt/Trabajando Juntos")
    if not _candidates:
        print("ERROR: no se encontro la carpeta 'Trabajando Juntos' montada bajo /sessions/*/mnt/")
        sys.exit(1)
    _mnt = os.path.dirname(_candidates[0])  # /sessions/<id>/mnt
    BASE = f"{_candidates[0]}/CAJAMAG/02_DASHBOARDS"
    AUTO = f"{BASE}/_automation"
    DL = f"{_mnt}/Downloads/"
    OUT_DIR = f"{_mnt}/outputs"

MASTER = f"{AUTO}/Dashboard_Master_DATA.html"
TV_MASTER = f"{AUTO}/TV_Master_DATA.html"

def effective_today(real_today=None):
    """Devuelve la fecha 'efectiva' que usa el pipeline para decidir cual es
    el 'mes en curso'. Regla ACTUALIZADA por Luis (17-sep-2026, reemplaza la
    regla anterior de 2 dias habiles): el tablero debe seguir mostrando la
    gestion/venta del mes que se ACABA DE CERRAR hasta el DIA 7 del mes
    siguiente (mas margen para que se terminen de cargar/ajustar en Bitrix
    las ultimas ventas y gestiones del mes que cierra). Del dia 1 al 7 del
    mes nuevo (inclusive), el pipeline trata el mes ANTERIOR como 'mes en
    curso' (YM, MES_NOMBRE, LABEL_SUFFIX); a partir del dia 8 ya usa el mes
    real. No pierde datos: cuando se vuelva a correr el pipeline despues del
    corte, el mes nuevo se recalcula completo (incluyendo los dias que ya
    habian pasado)."""
    t = real_today or date.today()
    if t.day <= 7:
        first_of_month = t.replace(day=1)
        return first_of_month - timedelta(days=1)  # ultimo dia del mes anterior
    return t


REAL_TODAY = date.today()
# 2-sep-2026, a pedido de Luis: override manual para saltar el buffer de dias habiles cuando el
# pide explicitamente cerrar el mes anterior y avanzar al nuevo ("actualiza el tablero y los
# dashboard hasta septiembre... si ya cerramos el mes de agosto ya no le tienes que colocar
# 'al 31' "). Uso: FORCE_TODAY=2026-09-02 python3 pipeline_master.py. Si no se define, se sigue
# usando la regla automatica de los 2 dias habiles (effective_today) sin cambios.
_FORCE_TODAY = os.environ.get('FORCE_TODAY')
TODAY = date.fromisoformat(_FORCE_TODAY) if _FORCE_TODAY else effective_today(REAL_TODAY)
YM = TODAY.strftime('%Y-%m')                       # ej. '2026-08'
MES_NOMBRE = ['','Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto',
              'Septiembre','Octubre','Noviembre','Diciembre'][TODAY.month]
LABEL_SUFFIX = f"(al {TODAY.day})"

def _norm_txt(s):
    if not s: return ''
    s = s.upper()
    for a, b in [('Á','A'), ('É','E'), ('Í','I'), ('Ó','O'), ('Ú','U'), ('Ñ','N')]:
        s = s.replace(a, b)
    return s

def clasificar_fiscal(servicio):
    """Regla confirmada por Luis (18-ago-2026): institutos de formacion tecnica /
    IFT, teatro y vacunacion no cobran IVA; cafeteria no cobra IVA (cobra INC 8%,
    impuesto distinto que no se resta aqui); todo lo demas (recreacion, deportes,
    cine, turismo, Teyuna salvo cafeteria, capacitaciones cortas, etc.) va gravado
    al 19%. Si se agregan nuevos servicios exentos, ajustar aqui."""
    s = _norm_txt(servicio)
    if 'FORMACION' in s or s.strip() == 'IFT' or s.startswith('IFT'):
        return 'exento_formacion'
    if 'TEATRO' in s:
        return 'exento_teatro'
    if 'VACUN' in s or 'TETANO' in s or 'HEPATITIS' in s:
        return 'exento_salud'
    if 'CAFETERIA' in s:
        return 'inc_cafeteria'
    return 'gravado_19'

def valor_sin_iva(t):
    cat = clasificar_fiscal(t.get('servicio'))
    v = t.get('valor') or 0.0
    return round(v/1.19, 2) if cat == 'gravado_19' else round(v, 2)

GESTION_MAP = {
    'Asesorías generales': 'Asesorías generales',
    'Presentación de Portafolio': 'Presentación de portafolio',
    'Empresa contactada por primera vez': 'Visita por primera vez',
    'Actualización de datos': 'Actualización de base de datos',
    'Actividades de mantenimiento': 'Actividades de mantenimiento',
    'Feria de servicios': 'Feria de servicios',
}
INDICATORS = ['Actividades de mantenimiento','Asesorías generales','Actualización de base de datos',
              'Visita por primera vez','Visitas presenciales','Feria de servicios',
              'Presentación de portafolio','Cotizaciones','Órdenes de compra']

# Metas mensuales por canal de contacto (Tipo de actividad V), confirmadas por
# Luis (25-ago-2026). "Visitas presenciales" NO esta aqui: reusa la meta que ya
# existe en profile_targets (mismo indicador que en la tarjeta de gestion
# general). Victoria Manjarres Jimenez (perfil 'IFT') queda exenta de estos 5
# indicadores de contactabilidad porque su perfil no aparece en este dict ni
# se le aplica la meta de Visitas presenciales (ver bucle de entries).
CANAL_TARGETS = {
    'Llamadas': {'Call Center': 300, 'Santa Marta': 100, 'Ciénaga': 70, 'Fundación': 60},
    'WhatsApp': {'Call Center': 400, 'Santa Marta': 120, 'Ciénaga': 90, 'Fundación': 70},
    'Correos': {'Call Center': 150, 'Santa Marta': 70, 'Ciénaga': 50, 'Fundación': 40},
    'Reuniones virtuales': {'Call Center': 4, 'Santa Marta': 3, 'Ciénaga': 2, 'Fundación': 2},
}

# ---------------- helpers ----------------
def parse_money(x):
    if pd.isna(x): return 0.0
    if isinstance(x,(int,float)): return float(x)
    s = str(x).strip()
    if s=='' or s.lower()=='nan': return 0.0
    return float(s.replace('.','').replace(',','.'))

def parse_date_ddmmyyyy(x):
    if pd.isna(x): return None
    s = str(x).strip()
    try:
        return datetime.strptime(s, '%d/%m/%Y').strftime('%Y-%m-%d')
    except Exception:
        return None

def clean_str(x):
    if pd.isna(x): return None
    s = str(x).strip()
    return s if s else None

def nit_str(x):
    if pd.isna(x): return None
    try:
        f = float(x)
        return str(int(f))
    except Exception:
        s = str(x).strip()
        return s if s else None

def line_total(r):
    # Preferir el detalle SKU (Precio x Cantidad) cuando existe; si el export no
    # trae SKU detallado para esa categoria/negociacion (p.ej. Empresarial a
    # veces no tiene lineas de producto), usar 'Ingreso' de la negociacion como
    # respaldo para no perder la venta (bug detectado 23-ago-2026: exports sin
    # SKU sumaban $0 en vez del valor real).
    # NOTA (9-sep-2026): los reportes de Bitrix (vistas 293/294/319) fueron
    # reconfigurados y ahora exportan columnas con nombres mas largos
    # ('Producto: Precio' en vez de 'Precio', etc.) -- se agregan los nombres
    # nuevos como primera opcion, con los viejos como respaldo por si algun
    # export futuro vuelve al formato corto.
    precio = r.get('Precio')
    if precio is None or pd.isna(precio):
        precio = r.get('Producto: Precio')
    if precio is not None and not pd.isna(precio):
        p = parse_money(precio)
        cant = r.get('Cantidad')
        if cant is None or pd.isna(cant):
            cant = r.get('Producto: Cantidad')
        try:
            c = float(cant) if not pd.isna(cant) else 1.0
        except Exception:
            c = 1.0
        return p * c
    total = r.get('Producto: Total')
    if total is not None and not pd.isna(total):
        return parse_money(total)
    ingreso = r.get('Ingreso')
    if ingreso is not None and not pd.isna(ingreso):
        return parse_money(ingreso)
    return 0.0

def load_data_blob(path):
    html = open(path, encoding='utf-8').read()
    d_start = html.index('const DATA = ') + len('const DATA = ')
    d_end = html.index('function fmt(n)')
    blob = html[d_start:d_end].strip()[:-1]
    return json.loads(blob), html, d_start, d_end

def load_tvdata_blob(path):
    html = open(path, encoding='utf-8').read()
    i = html.index('window.TVDATA')
    i2 = html.index('=', i) + 1
    s = html[i2:]
    lead_ws = len(s) - len(s.lstrip())
    start = i2 + lead_ws
    depth, end = 0, None
    for idx in range(start, len(html)):
        ch = html[idx]
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = idx + 1
                break
    blob = html[start:end]
    return json.loads(blob), html, start, end

# ============ 1. Cargar master ============
DATA, _, _, _ = load_data_blob(MASTER)
TVDATA, _, _, _ = load_tvdata_blob(TV_MASTER)

# ============ 1b. Cerrar meses anteriores (2-sep-2026, a pedido de Luis) ============
# Bug corregido: las etiquetas "(al N)"/"*" y el flag 'parcial' se ponian una sola vez, cuando
# ese mes era "el mes en curso" en su momento, y se quedaban pegadas para siempre -- Julio se
# quedo con "*" y Agosto con "(al 31)" aun despues de cerrados ("si ya cerramos el mes ya no le
# tienes que colocar 'al 31' porque se asume que eso es lo del mes"). Esta corrida es
# auto-reparable: en CADA ejecucion, cualquier mes que no sea el YM que se esta procesando ahora
# mismo se regenera con su nombre limpio (sin sufijo) y sin marca de parcial -- asi el mes que
# hoy es "en curso" se cierra solo la proxima vez que el pipeline avance al mes siguiente.
def _mes_limpio(ym):
    return MES_NOMBRE_LIST[int(ym.split('-')[1])]

MES_NOMBRE_LIST = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto',
                   'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
# FORCE_CLOSE_CURRENT=1: ademas de los meses anteriores, cierra tambien el YM que se esta
# procesando en esta misma corrida. Uso puntual (2-sep-2026): Luis confirmo explicitamente que
# agosto ya esta cerrado, pero aun no hay export de Bitrix de septiembre (individual.xls/
# empresarial.xls/ift.xls/gestiones.xls en Downloads siguen fechados 01-31 agosto) -- forzar YM a
# septiembre sin datos reales crearia un mes de $0 enganoso. Se cierra agosto explicitamente en
# vez de eso, sin inventar un septiembre vacio.
_FORCE_CLOSE_CURRENT = os.environ.get('FORCE_CLOSE_CURRENT') == '1'
def _es_mes_a_cerrar(ym):
    return ym != YM or _FORCE_CLOSE_CURRENT

for _ym in list(DATA['gestiones']['month_labels'].keys()):
    if _es_mes_a_cerrar(_ym):
        DATA['gestiones']['month_labels'][_ym] = _mes_limpio(_ym)
for _ym in list(DATA['ventas']['mes_labels'].keys()):
    if _es_mes_a_cerrar(_ym):
        DATA['ventas']['mes_labels'][_ym] = _mes_limpio(_ym)
for _t in DATA['ventas']['tendencia']:
    if _es_mes_a_cerrar(_t['ym']):
        _t['parcial'] = False
        _t.pop('meta_nota', None)
        _t['fuente'] = re.sub(r',?\s*\(al \d+\)', '', _t.get('fuente') or '').strip()
for _ym in list(TVDATA.get('month_labels', {}).keys()):
    if _es_mes_a_cerrar(_ym):
        TVDATA['month_labels'][_ym] = _mes_limpio(_ym)
print(f"Cierre de meses anteriores aplicado (todo mes != {YM} sin marcas de parcial{' + YM actual (FORCE_CLOSE_CURRENT)' if _FORCE_CLOSE_CURRENT else ''}).")

# ============ 2. Quitar el mes en curso del master (si ya existía, para no duplicar) ============
DATA['gestiones']['raw_gestiones'] = [r for r in DATA['gestiones']['raw_gestiones'] if not r['fecha'].startswith(YM)]
DATA['ventas']['transacciones'] = [t for t in DATA['ventas']['transacciones'] if t['ym'] != YM]
DATA['ventas']['tendencia'] = [t for t in DATA['ventas']['tendencia'] if t['ym'] != YM]
if YM in DATA['ventas']['meses_order']:
    DATA['ventas']['meses_order'].remove(YM)
for a in DATA['gestiones']['advisors_full']:
    a['months'].pop(YM, None)
    if YM in (a.get('active_months') or []):
        a['active_months'].remove(YM)

# ============ 3. Parsear pulls frescos de Bitrix (mes en curso, día 1 -> hoy) ============
adv_zona = {}
for t in DATA['ventas']['transacciones']:
    if t.get('zona'):
        adv_zona.setdefault(t['asesor'], t['zona'])

new_tx = []

# Deal IDs marcados como posible_duplicado=true en Supabase bitrix_eventos
# dentro de la ventana de este pull (consultado 20-ago-2026). Se excluyen del
# merge para no inflar las cifras de ventas con negociaciones duplicadas.
DEDUP_DEAL_IDS = {'29104', '29033'}  # corregido 11-sep-2026: se retira 29197 (falso positivo confirmado via soporte de pago)
# Nota (21-ago-2026): se retiro '29281' de este set. Luis confirmo que la venta real
# de Maria Jose Garcia Guaman de agosto es $5.442.100, que solo cuadra incluyendo el
# negocio 29281 (Alquiler de Salon, $226.400, creado 19/08). Estaba marcado como
# posible_duplicado en Supabase junto con otros 3 negocios creados el 18/08, pero
# no hay evidencia de que sea un duplicado real (unico negocio de ese asesor/monto/
# fecha) — parece un falso positivo de la deteccion de duplicados de esa fecha.
# Los otros 3 (29197, 29104, 29033) siguen excluidos hasta confirmar con Luis si
# tambien son falsos positivos del mismo lote del 18-ago.

def parse_ventas(fname, tipo_venta, categoria_default, etapa_ok, fuente_tag):
    path = DL + fname
    df = pd.read_html(path)[0]
    rows = []
    excluded = 0
    for _, r in df.iterrows():
        if str(r.get('ID')).strip() in DEDUP_DEAL_IDS:
            excluded += 1
            continue
        etapa_val = r.get('Etapa de la negociación')
        if etapa_val is None or pd.isna(etapa_val):
            etapa_val = r.get('Etapa')
        if etapa_val != etapa_ok: continue
        fecha = parse_date_ddmmyyyy(r.get('Fecha de facturación'))
        if fecha is None or not fecha.startswith(YM): continue
        asesor = clean_str(r.get('Persona responsable')) or clean_str(r.get('Responsable'))
        cliente = ' '.join([p for p in [clean_str(r.get('Contacto: Nombre')) or clean_str(r.get('Contacto: Primer nombre')), clean_str(r.get('Contacto: Apellido'))] if p]) or None
        empresa = clean_str(r.get('Compañía: Nombre de la compañía'))
        servicio = clean_str(r.get('Servicios a cotizar')) or clean_str(r.get('Servicios a utilizar')) or clean_str(r.get('Producto'))
        categoria = categoria_default
        if tipo_venta == 'Individual' and categoria_default == 'A':
            categoria = clean_str(r.get('Contacto: Categoría de afiliación')) or 'A'
        rows.append({
            'ym': fecha[:7], 'fecha': fecha, 'asesor': asesor,
            'zona': adv_zona.get(asesor, 'Santa Marta'),
            'tipo_venta': 'Individual' if tipo_venta in ('Individual','IFT') else tipo_venta,
            'categoria': categoria, 'servicio': servicio, 'valor': line_total(r),
            'fuente': fuente_tag, 'cliente': cliente or empresa,
            'nit': nit_str(r.get('Contacto: Nit empresa')) or nit_str(r.get('Compañía: Nit')),
            'empresa': empresa, 'detalle': clean_str(r.get('Producto')),
            'cantidad': (r.get('Cantidad') if not pd.isna(r.get('Cantidad')) else 1),
        })
    if excluded:
        print(f'  [{fname}] excluidas {excluded} filas por posible_duplicado (Supabase)')
    return rows

new_tx += parse_ventas('individual.xls', 'Individual', 'A', 'CERRADO GANADO', f'Bitrix (Individual) - {MES_NOMBRE} {TODAY.year} (al {TODAY.day})')
new_tx += parse_ventas('empresarial.xls', 'Empresarial', 'E', 'CERRADO GANADO', f'Bitrix (Empresarial) - {MES_NOMBRE} {TODAY.year} (al {TODAY.day})')
new_tx += parse_ventas('ift.xls', 'IFT', 'Formación para el trabajo (IFT)', 'CERRADO MATRICULARO', f'Bitrix (IFT) - {MES_NOMBRE} {TODAY.year} (al {TODAY.day})')

print('ventas nuevas (mes en curso):', len(new_tx), 'total $', sum(t['valor'] for t in new_tx))

# Etapas que cuentan como "ya sucedido" (confirmado por Luis, 1-sep-2026): cierre
# de negociacion (ganado o perdido) o ejecucion de evento. Se excluyen
# explicitamente planificacion/evento aplazado y cualquier etapa de "en curso"
# de los demas pipelines (ver docstring arriba).
ETAPAS_OK = {'EJECUCION EVENTO', 'CERRADO GANADO', 'CERRADO PERDIDO'}  # ya sin tildes (comparado via _norm_txt)

g = pd.read_html(DL + 'gestiones.xls')[0]
new_raw_gestiones = []
excluidas_por_etapa = 0
for _, r in g.iterrows():
    fecha = parse_date_ddmmyyyy(r['Fecha y hora evento'])
    if fecha is None or not fecha.startswith(YM): continue
    etapa = clean_str(r.get('Etapa de la negociación'))
    if etapa is not None and _norm_txt(etapa) not in ETAPAS_OK:
        excluidas_por_etapa += 1
        continue
    new_raw_gestiones.append({
        'fecha': fecha, 'asesor': clean_str(r['Persona responsable']),
        'empresa': clean_str(r['Compañía: Nombre de la compañía']),
        'nit': nit_str(r['Compañía: Nit']),
        'medio': clean_str(r['Tipo de actividad (V)']),
        'gestion': clean_str(r['Tipo de evento (V)']),
        'comentario': clean_str(r['Descripción del evento (V)']),
        'etapa': etapa,
        'pipeline': clean_str(r.get('Pipeline de la negociación')),
    })
if excluidas_por_etapa:
    print(f'  [gestiones.xls] excluidas {excluidas_por_etapa} filas por etapa no valida (planificacion/aplazado/etc.)')
print('gestiones nuevas (mes en curso):', len(new_raw_gestiones))

# ============ 4. Merge en DATA ============
new_raw_gestiones_sorted = sorted(new_raw_gestiones, key=lambda r: r['fecha'], reverse=True)
DATA['gestiones']['raw_gestiones'] = new_raw_gestiones_sorted + DATA['gestiones']['raw_gestiones']
DATA['ventas']['transacciones'] = DATA['ventas']['transacciones'] + new_tx

if YM not in DATA['gestiones']['months']:
    DATA['gestiones']['months'].append(YM)
DATA['gestiones']['month_labels'][YM] = MES_NOMBRE if _FORCE_CLOSE_CURRENT else f'{MES_NOMBRE} {TODAY.year} {LABEL_SUFFIX}'

raw_all = DATA['gestiones']['raw_gestiones']
profile_targets = DATA['gestiones']['profile_targets']
ef = DATA['empresas_full']
month_raw = [r for r in raw_all if r['fecha'].startswith(YM)]
today_str = raw_all[0]['fecha'] if raw_all else None

af = DATA['gestiones']['advisors_full']
for a in af:
    name = a['name']
    perfil = a.get('current_profile')
    rows = [r for r in month_raw if r['asesor']==name]
    if not rows:
        continue
    counts = Counter()
    for r in rows:
        for p in [x.strip() for x in (r.get('gestion') or '').split('/')]:
            if p in GESTION_MAP:
                counts[GESTION_MAP[p]] += 1
        if r.get('medio') and r['medio'].strip() == 'Visita presencial':
            counts['Visitas presenciales'] += 1
    targets = profile_targets.get(perfil, {})
    inds, pct_vals = {}, []
    for ind in INDICATORS:
        meta = targets.get(ind)
        if ind in ('Cotizaciones','Órdenes de compra'):
            inds[ind] = {'meta': meta, 'real': None, 'pct': None, 'na': True, 'reason': 'sin_dato'}
            continue
        real = counts.get(ind, 0)
        if meta is None:
            inds[ind] = {'meta': None, 'real': real, 'pct': None, 'na': True}
        else:
            pct = round(real/meta, 4) if meta else 0.0
            inds[ind] = {'meta': meta, 'real': real, 'pct': pct, 'na': False}
            pct_vals.append(pct)
    global_pct = round(sum(pct_vals)/len(pct_vals), 4) if pct_vals else 0.0
    a['months'][YM] = {'perfil': perfil, 'indicators': inds, 'global_pct': global_pct}
    # Root cause del bug reportado por Luis (31-ago-2026): 'months[YM]' se llenaba bien cada
    # ciclo pero 'active_months' (usado por el selector de mes en Gestion>Equipo y por la
    # columna "Hasta" de Actividad del equipo) nunca se extendia con el mes en curso, asi que
    # el mes actual siempre aparecia vacio/"Hasta" se quedaba congelado en el mes anterior.
    am = a.setdefault('active_months', [])
    if YM not in am:
        am.append(YM)
        am.sort()
    a['meses_activos'] = len(am)

for a in af:
    name = a['name']
    assigned = [e for e in ef if e.get('ase')==name]
    assigned_nits = set(e['nit'] for e in assigned if e.get('nit'))
    gestion_nits = set(r['nit'] for r in raw_all if r['asesor']==name and r.get('nit'))
    overlap = assigned_nits & gestion_nits
    a['empresas_asignadas'] = len(assigned)
    a['empresas_gestionadas_contrato'] = len(overlap)
    a['empresas_faltantes_contrato'] = len(assigned) - len(overlap)

last_by_advisor = {}
for r in raw_all:
    if r['asesor'] not in last_by_advisor:
        last_by_advisor[r['asesor']] = r
for name, h in DATA['historia_asesor'].items():
    last = last_by_advisor.get(name)
    if last and today_str:
        dias = (datetime.strptime(today_str,'%Y-%m-%d') - datetime.strptime(last['fecha'],'%Y-%m-%d')).days
        h['ultima_gestion'] = last['fecha']
        h['dias_sin_cargar_gestion'] = dias

# ============ 5. Agregados de ventas ============
month_tx = [t for t in DATA['ventas']['transacciones'] if t['ym']==YM]
month_total = sum(t['valor'] for t in month_tx)

# Meta del mes en curso: el contrato corre exactamente del 12-mar-2026 al 11-sep-2026 y
# suma 590,000,000 en total (confirmado por Luis, 3-sep-2026). Todos los meses PLENAMENTE
# dentro del contrato (abril-agosto) usan la tasa plana meta_contractual_mensual (590M/6).
# Pero septiembre 2026 es el mes de CIERRE del contrato y solo incluye 11 de sus 30 dias
# (1 al 11-sep) -- asignarle la tasa plana completa infla el acumulado a 650M en vez de
# 590M. Se le asigna el RESIDUAL exacto (590M menos lo ya asignado a los meses previos,
# incluido marzo que ya trae su propia meta prorateada por antiguedad del equipo) para que
# la meta acumulada del contrato complete exactamente 590,000,000 al cierre.
CONTRATO_TOTAL = 590000000
CONTRATO_FIN_YM = '2026-09'
if YM == CONTRATO_FIN_YM:
    _metas_previas = sum(t['meta'] for t in DATA['ventas']['tendencia'] if t['ym'] < YM)
    meta_mes_actual = round(CONTRATO_TOTAL - _metas_previas, 2)
else:
    meta_mes_actual = DATA['ventas']['meta_contractual_mensual']

_tend_entry = {
    'ym': YM, 'mes': MES_NOMBRE, 'ventas': month_total,
    'meta': meta_mes_actual,
    'fuente': f'Bitrix (Individual + Empresarial + IFT) - {MES_NOMBRE} {TODAY.year}',
    'parcial': False,
} if _FORCE_CLOSE_CURRENT else {
    'ym': YM, 'mes': MES_NOMBRE, 'ventas': month_total,
    'meta': meta_mes_actual,
    'fuente': f'Bitrix (Individual + Empresarial + IFT) - {MES_NOMBRE} {TODAY.year}, {LABEL_SUFFIX}',
    'parcial': True,
    'meta_nota': f'Corte parcial: solo incluye ventas cerradas y facturadas hasta el {TODAY.day} de {MES_NOMBRE.lower()}.' + (
        ' Meta de septiembre prorateada: el contrato cierra el 11-sep-2026, asi que solo cuenta esa porcion del mes.' if YM == CONTRATO_FIN_YM else ''
    )
}
DATA['ventas']['tendencia'].append(_tend_entry)
DATA['ventas']['meses_order'].append(YM)
DATA['ventas']['mes_labels'][YM] = MES_NOMBRE if _FORCE_CLOSE_CURRENT else f'{MES_NOMBRE} {LABEL_SUFFIX}'

existing_servicios = set(DATA['ventas']['filtros']['servicios'])
new_servicios = sorted(set(t['servicio'] for t in month_tx if t['servicio']) - existing_servicios)
DATA['ventas']['filtros']['servicios'] = sorted(existing_servicios | set(new_servicios))
for key in ['categorias','asesores','zonas','tipos_venta']:
    field = {'categorias':'categoria','asesores':'asesor','zonas':'zona','tipos_venta':'tipo_venta'}[key]
    existing = set(DATA['ventas']['filtros'][key])
    new_vals = sorted(set(t[field] for t in month_tx if t.get(field)) - existing)
    if new_vals:
        DATA['ventas']['filtros'][key] = sorted(existing | set(new_vals))

DATA['empresas_agg']['tam_counts'] = dict(Counter(r['tam'] for r in DATA['empresas_full']))

# ============ 6. Guardar master actualizado ============
new_data_json = json.dumps(DATA, ensure_ascii=False, separators=(',',':'))
master_html = open(MASTER, encoding='utf-8').read()
d_start = master_html.index('const DATA = ')
d_end = master_html.index('function fmt(n)')
master_html2 = master_html[:d_start] + 'const DATA = ' + new_data_json + ';\n' + master_html[d_end:]
open(MASTER, 'w', encoding='utf-8').write(master_html2)
print('master DATA actualizado:', MASTER)

# ============ 7. Recalcular TVDATA (ranking + gestion_groups + contactadas_por_mes) ============
# Antes esto usaba '2026-07' fijo como mes de referencia para heredar zona/meta;
# se corrigio (25-ago-2026) para que siempre tome el mes mas reciente ya
# cargado ANTES del mes en curso, y asi no vuelva a quedar obsoleto cada vez
# que pasa un mes (esa era la causa raiz de que asesores nuevos, como Karen
# Liseth, aparecieran con zona/meta en null: heredaban de un mes en el que
# todavia no existian).
prev_keys = sorted(k for k in TVDATA['ranking_by_period'].keys() if k != 'acumulado' and k < YM)
prev_rank = {r['asesor']: r for r in TVDATA['ranking_by_period'].get(prev_keys[-1], [])} if prev_keys else {}
af_by_name = {a['name']: a for a in af}
totals_by_adv = Counter()
for t in month_tx:
    if t.get('asesor'):
        totals_by_adv[t['asesor']] += t['valor']
rank_month = []
names_seen = set(totals_by_adv.keys()) | set(prev_rank.keys())
for name in names_seen:
    prev = prev_rank.get(name, {})
    meta, zona, meses_activos = prev.get('meta'), prev.get('zona'), prev.get('meses_activos')
    if not prev:
        # Asesor nuevo (sin registro previo en el ranking de ventas): heredar
        # su zona real desde advisors_full en vez de dejarla en null, y
        # asignarle la meta prorateada de "primer mes" (21M), confirmada por
        # Luis para Jessica Luque Garcia y Karen Liseth Cantillo De la Cruz -
        # mismo cohorte de arranque, sin importar la zona.
        adv = af_by_name.get(name)
        zona = adv.get('current_profile') if adv else None
        meta = 21000000
        meses_activos = 1
    total = totals_by_adv.get(name, 0.0)
    cumpl = round(total/meta*100, 1) if meta else None
    rank_month.append({'asesor': name, 'zona': zona, 'meta': meta, 'total': total,
                        'cumpl': cumpl, 'meses_activos': meses_activos})
rank_month.sort(key=lambda r: -(r['cumpl'] or 0))
TVDATA['ranking_by_period'][YM] = rank_month

# El ranking 'acumulado' nunca se reconstruye desde cero (mas abajo solo se
# refresca el total/cumpl de quienes YA estan en la lista) — asi que un
# asesor nuevo (p.ej. Karen Liseth, primer mes en agosto) se quedaba afuera
# de esa vista para siempre. Se agrega aqui una sola vez, con su total de
# este mes como punto de partida de su acumulado.
acum_names = {r['asesor'] for r in TVDATA['ranking_by_period']['acumulado']}
for r in rank_month:
    if r['asesor'] not in acum_names:
        TVDATA['ranking_by_period']['acumulado'].append(dict(r))

# ---- Ventas por categoria (empresarial vs individual) para la pantalla del TV ----
# Recalcula el mes en curso a partir de las transacciones frescas, y también
# recompone 'acumulado' sumando TODOS los meses cargados (ranking_by_period
#['acumulado'] históricamente se quedaba desactualizado porque nada lo
# recalculaba tras el primer corte del contrato; aquí se corrige cada corrida
# para que ranking y ventas-por-categoria muestren siempre el mismo total).
if 'ventas_categoria_by_period' not in TVDATA:
    TVDATA['ventas_categoria_by_period'] = {}
cat_month = Counter()
tipo_month = Counter()  # (asesor,tipo) -> valor
sin_iva_month = Counter()  # asesor -> valor sin iva
for t in month_tx:
    if t.get('asesor') and t.get('tipo_venta') in ('Empresarial', 'Individual'):
        tipo_month[(t['asesor'], t['tipo_venta'])] += t['valor']
        sin_iva_month[t['asesor']] += valor_sin_iva(t)
vc_month = []
for r in rank_month:
    name = r['asesor']
    emp = round(tipo_month.get((name, 'Empresarial'), 0.0), 2)
    ind = round(tipo_month.get((name, 'Individual'), 0.0), 2)
    vc_month.append({'asesor': name, 'zona': r['zona'], 'meta': r['meta'],
                      'empresarial': emp, 'individual': ind, 'total': round(emp+ind, 2),
                      'sin_iva': round(sin_iva_month.get(name, 0.0), 2)})
TVDATA['ventas_categoria_by_period'][YM] = vc_month

all_tipo = Counter()
all_sin_iva = Counter()
for t in DATA['ventas']['transacciones']:
    if t.get('asesor') and t.get('tipo_venta') in ('Empresarial', 'Individual') and t.get('ym') in TVDATA['meses'] + [YM]:
        all_tipo[(t['asesor'], t['tipo_venta'])] += t['valor']
        all_sin_iva[t['asesor']] += valor_sin_iva(t)
acc_by_adv = Counter()
for (name, tipo), v in all_tipo.items():
    acc_by_adv[name] += v
vc_acum = []
for r in TVDATA['ranking_by_period']['acumulado']:
    name = r['asesor']
    emp = round(all_tipo.get((name, 'Empresarial'), 0.0), 2)
    ind = round(all_tipo.get((name, 'Individual'), 0.0), 2)
    total = round(emp+ind, 2)
    vc_acum.append({'asesor': name, 'zona': r['zona'], 'meta': r['meta'],
                     'empresarial': emp, 'individual': ind, 'total': total,
                     'sin_iva': round(all_sin_iva.get(name, 0.0), 2)})
    # Mantiene el total/cumpl del ranking acumulado sincronizado con la suma real
    # (evita que vuelva a quedar desactualizado como se encontró el 18-ago-2026).
    if r.get('meta'):
        r['total'] = total
        r['cumpl'] = round(total/r['meta']*100, 1)
TVDATA['ventas_categoria_by_period']['acumulado'] = vc_acum

entries = []
for a in af:
    name = a['name']
    if YM not in a['months']:
        continue
    m = a['months'][YM]
    assigned = [e for e in ef if e.get('ase')==name]
    assigned_nits = set(e['nit'] for e in assigned if e.get('nit'))
    gestion_nits_all = set(r['nit'] for r in raw_all if r['asesor']==name and r.get('nit'))
    overlap = assigned_nits & gestion_nits_all
    my_rows_all = [r for r in raw_all if r['asesor']==name]
    last = my_rows_all[0] if my_rows_all else None
    dias = None
    if last and today_str:
        dias = (datetime.strptime(today_str,'%Y-%m-%d') - datetime.strptime(last['fecha'],'%Y-%m-%d')).days
    inds_pct100 = {k: {**v, 'pct': (v['pct']*100 if v['pct'] is not None else None)} for k,v in m['indicators'].items()}
    # Conteo por canal (Tipo de actividad V) del mes en curso, con meta mensual
    # por perfil/zona confirmada por Luis (25-ago-2026). Victoria Manjarres
    # Jimenez (perfil 'IFT') queda exenta de estos 5 indicadores de
    # contactabilidad a pedido explicito de Luis (no aparece en CANAL_TARGETS
    # ni se le aplica la meta de 'Visitas presenciales' aqui, aunque su perfil
    # IFT si tenga una meta de visitas para el indicador general de gestion).
    perfil = m['perfil']
    targets = profile_targets.get(perfil, {})
    canal_rows = [r for r in month_raw if r['asesor']==name]
    canal_counter = Counter((r.get('medio') or '').strip() for r in canal_rows)
    canal_reales = {
        'Llamadas': canal_counter.get('Llamada', 0),
        'Visitas presenciales': canal_counter.get('Visita presencial', 0),
        'WhatsApp': canal_counter.get('WhatsApp', 0),
        'Correos': canal_counter.get('Correo electrónico', 0),
        'Reuniones virtuales': canal_counter.get('Reunión virtual', 0),
    }
    canales = {}
    for canal_nombre, real_val in canal_reales.items():
        if canal_nombre == 'Visitas presenciales':
            meta_val = targets.get('Visitas presenciales') if perfil != 'IFT' else None
        else:
            meta_val = CANAL_TARGETS.get(canal_nombre, {}).get(perfil)
        if meta_val is None:
            canales[canal_nombre] = {'real': real_val, 'meta': None, 'pct': None, 'na': True}
        else:
            pct = round(real_val/meta_val*100, 1) if meta_val else 0.0
            canales[canal_nombre] = {'real': real_val, 'meta': meta_val, 'pct': pct, 'na': False}
    # % de cumplimiento promedio objetivo (25-ago-2026, a pedido de Luis):
    # combina los indicadores de gestion (sin 'Visitas presenciales', que ya
    # se saco de la tarjeta para no duplicarla con la fila de canales) + los
    # indicadores de canales/medios de contacto que tengan meta aplicable
    # (Llamadas, Visitas presenciales, WhatsApp, Correos, Reuniones virtuales
    # - o menos si el asesor esta exento, como Victoria Manjarres en IFT).
    combined_pcts = []
    for k, v in m['indicators'].items():
        if k == 'Visitas presenciales':
            continue
        if not v.get('na') and v.get('pct') is not None:
            combined_pcts.append(v['pct'] * 100)
    for v in canales.values():
        if not v.get('na') and v.get('pct') is not None:
            combined_pcts.append(v['pct'])
    global_pct_obj = round(sum(combined_pcts) / len(combined_pcts), 1) if combined_pcts else 0.0
    entries.append({
        'name': name, 'zona': m['perfil'], 'active': a.get('active', True),
        'global_pct': global_pct_obj, 'indicators': inds_pct100,
        'canales': canales,
        'empresas_asignadas': len(assigned), 'empresas_gestionadas': len(overlap),
        'empresas_faltantes': len(assigned) - len(overlap),
        'ultima_gestion': last['fecha'] if last else None,
        'dias_sin_cargar_gestion': dias,
    })
entries.sort(key=lambda e: -e['global_pct'])
TVDATA['gestion_groups_by_period'][YM] = [entries[i:i+3] for i in range(0, len(entries), 3)]

# ---- Detalle de empresas por asesor (para las tarjetas de Empresas del Tablero TV) ----
# Usa el campo 'per' de empresas_full, que ya clasifica cada empresa exactamente
# igual que la pantalla de Empresas (Contactada - contrato actual / Contactada -
# solo contrato anterior / No contactada), asi que no hace falta reconciliar nits
# a mano otra vez. Es una foto global (no cambia por mes) porque empresas_full
# tampoco tiene historia mes a mes, solo el estado actual del contrato.
#
# IMPORTANTE (27-ago-2026, root cause de "las empresas del Tablero se
# desactualizan"): este bloque tenia una copia MAS VIEJA de esta logica que
# la de recompute_tv_empresas.py -- le faltaban 'cadencia', 'cadencia_pendientes',
# 'iloc_mes' y 'dia_stats_visitas' (agregados despues solo alla, nunca portados
# aqui). Como pipeline_master.py es el que corre en CADA refresco completo de
# Bitrix, cada vez que se hacia un repull esta version vieja pisaba/borraba
# esos campos aunque recompute_tv_empresas.py se hubiera corrido antes,
# haciendo que "Empresas Atendidas"/"Empresas por Atender" volvieran a 0/0 en
# el Tablero. Se sincroniza aqui EXACTAMENTE igual que en recompute_tv_empresas.py
# para que los dos scripts nunca vuelvan a divergir.
TAM_RANK = {'Grande':0, 'Mediana':1, 'Pequeña':2, 'Micro':3}
TAM_ORDER_ALL = ['Grande', 'Mediana', 'Pequeña', 'Micro']
CADENCIA_MENSUAL = {'Grande', 'Mediana'}
CADENCIA_DIAS = {'Pequeña': 60}
CADENCIA_CONTRATO = {'Micro'}
def norm_tam(t):
    t = t or 'Sin dato'
    return 'Micro' if t == 'Sin dato' else t
def dias_desde(fecha_str):
    if not fecha_str:
        return None
    try:
        d = datetime.strptime(fecha_str[:10], '%Y-%m-%d').date()
    except ValueError:
        return None
    # Usa REAL_TODAY (fecha real de hoy), no la TODAY 'efectiva' congelada por
    # la regla de cierre de mes: la cadencia (dias sin gestion) siempre debe
    # reflejar el tiempo real transcurrido, no el mes que se esta mostrando.
    return (REAL_TODAY - d).days
tam_by_nit_global = {e['nit']: norm_tam(e.get('tam')) for e in ef if e.get('nit')}
ultima_gestion_por_nit = {}
for r in raw_all:
    nit = r.get('nit')
    if not nit:
        continue
    if nit not in ultima_gestion_por_nit or r['fecha'] > ultima_gestion_por_nit[nit]:
        ultima_gestion_por_nit[nit] = r['fecha']
nits_gestionadas_alguna_vez = set(ultima_gestion_por_nit.keys())
detalle_por_asesor = {}
for a in af:
    name = a['name']
    rows = [e for e in ef if e.get('ase')==name]
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
    my_gestion_rows = [r for r in raw_all if r['asesor']==name and r.get('nit')]
    gestiones_by_tam = Counter()
    for r in my_gestion_rows:
        gestiones_by_tam[tam_by_nit_global.get(r['nit'], 'Micro')] += 1

    # Ilocalizables asignadas a este asesor (campo 'iloc' de empresas_full, ya
    # calculado por build_operativo.py sobre el export COMPANY mas reciente).
    ilocalizadas_rows = [e for e in rows if e.get('iloc')]
    ilocalizadas_by_tam = Counter(norm_tam(e.get('tam')) for e in ilocalizadas_rows)

    # Empresas atendidas ESTE MES (no el estado global del contrato) por
    # tamaño, y ritmo diario (promedio/minimo/maximo de empresas distintas
    # gestionadas por dia habil) de este asesor puntual.
    my_month_rows = [r for r in month_raw if r.get('asesor')==name]
    my_month_nits = set(r['nit'] for r in my_month_rows if r.get('nit'))
    atendidas_mes_by_tam = Counter(tam_by_nit_global.get(n, 'Micro') for n in my_month_nits)
    por_dia_asesor = defaultdict(set)
    for r in my_month_rows:
        if r.get('nit'):
            por_dia_asesor[r['fecha']].add(r['nit'])
    dia_vals = [len(s) for s in por_dia_asesor.values()]
    dia_stats_asesor = {
        'promedio': round(sum(dia_vals)/len(dia_vals), 1) if dia_vals else 0,
        'minimo': min(dia_vals) if dia_vals else 0,
        'maximo': max(dia_vals) if dia_vals else 0,
        'dias_con_gestion': len(dia_vals),
    } if dia_vals else None

    # Mismo ritmo diario pero SOLO contando visitas presenciales.
    my_month_visitas = [r for r in my_month_rows if (r.get('medio') or '').strip() == 'Visita presencial']
    por_dia_visitas = defaultdict(set)
    for r in my_month_visitas:
        if r.get('nit'):
            por_dia_visitas[r['fecha']].add(r['nit'])
    dia_vals_visitas = [len(s) for s in por_dia_visitas.values()]
    dia_stats_visitas = {
        'promedio': round(sum(dia_vals_visitas)/len(dia_vals_visitas), 1) if dia_vals_visitas else 0,
        'minimo': min(dia_vals_visitas) if dia_vals_visitas else 0,
        'maximo': max(dia_vals_visitas) if dia_vals_visitas else 0,
        'dias_con_gestion': len(dia_vals_visitas),
    } if dia_vals_visitas else None

    # Ilocalizables encontradas EN GESTIONES DE ESTE MES, con nombres.
    iloc_mes_rows = [r for r in my_month_rows if 'ilocaliz' in (r.get('gestion') or '').lower()]
    iloc_mes_nombres = sorted(set(r.get('empresa') for r in iloc_mes_rows if r.get('empresa')))
    iloc_mes = {'total': len(iloc_mes_nombres), 'nombres': iloc_mes_nombres}

    # Cadencia de visitas por la directriz de frecuencia segun tamaño
    # (Grande/Mediana: 1 gestion este mes; Pequeña: ultima gestion <=60 dias;
    # Micro: al menos 1 gestion en todo el contrato).
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
            else:
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
TVDATA['empresas']['detalle_por_asesor'] = detalle_por_asesor

tam_by_nit = {e['nit']: (e['tam'] or 'Sin dato') for e in ef if e.get('nit')}
month_nits = set(r['nit'] for r in month_raw if r.get('nit'))
tam_counter = Counter()
for n in month_nits:
    tam = tam_by_nit.get(n, 'Sin dato')
    if tam == 'Sin dato': tam = 'Micro'
    tam_counter[tam] += 1
TVDATA['empresas']['contactadas_por_mes'][YM] = dict(tam_counter)
TVDATA['empresas']['contactadas_por_mes_total'][YM] = sum(tam_counter.values())

# ---- Empresas por dia (promedio / minimo / maximo de empresas distintas
# gestionadas por dia habil, contando por NIT unico dentro del mes en curso) ----
from collections import defaultdict
por_dia = defaultdict(set)
for r in month_raw:
    if r.get('nit'):
        por_dia[r['fecha']].add(r['nit'])
dia_counts = {d: len(s) for d, s in por_dia.items()}
if dia_counts:
    vals = list(dia_counts.values())
    TVDATA['empresas']['dia_stats'] = TVDATA['empresas'].get('dia_stats', {})
    TVDATA['empresas']['dia_stats'][YM] = {
        'promedio': round(sum(vals)/len(vals), 1),
        'minimo': min(vals), 'maximo': max(vals),
        'dias_con_gestion': len(vals),
        'por_dia': dict(sorted(dia_counts.items())),
    }

# ---- Empresas ilocalizables (a nivel equipo, tomado de empresas_agg ya
# calculado por build_operativo.py/build_gerencial.py sobre el export COMPANY
# mas reciente) ----
eagg = DATA.get('empresas_agg') or {}
equipo_counts = eagg.get('equipo_counts') or {}
total_iloc = sum((v.get('iloc') or 0) for v in equipo_counts.values())
TVDATA['empresas']['ilocalizables'] = {
    'total': total_iloc,
    'por_equipo': {k: v.get('iloc', 0) for k, v in equipo_counts.items()},
    'top': (eagg.get('top_iloc') or [])[:12],
}

if YM not in TVDATA['meses']:
    TVDATA['meses'].append(YM)
TVDATA['month_labels'][YM] = MES_NOMBRE if _FORCE_CLOSE_CURRENT else f'{MES_NOMBRE} {LABEL_SUFFIX}'

# ---- Ventas por servicio (para la pagina 'Ventas por Servicio' del Tablero
# TV, pedida por los asesores). 27-ago-2026, a pedido de Luis: esta pagina
# tenia su PROPIA clasificacion por palabras clave sobre el texto crudo
# (ej. "CINE" o "AUDITORIO" sueltos), totalmente independiente y desactualizada
# frente al catalogo OFICIAL de 29 servicios (+ IVA) que Luis mando por imagen
# y que ya usan Operativo y Gerencial (build_operativo.py Paso 10 / SEGURO DE
# VIDA -> Turismo). Eso hacia que el Tablero mostrara categorias distintas
# ("Cine/Cinemark", "Salidas Pedagogicas", "Alquiler auditorio/salon" como si
# fueran servicios propios, cuando oficialmente son todos variantes de
# "Recreacion" por zona) y sin la correccion de Seguro de vida. Se reemplaza
# por EXACTAMENTE la misma resolucion oficial (mismo catalogo, mismos mapeos
# de zona/Teyuna) para que las 3 vistas (Operativo/Gerencial/Tablero TV)
# siempre muestren la misma clasificacion de servicios.
IMPUESTO_OFICIAL = {
    'ADULTO MAYOR': 19, 'VACUNACION SANTA MARTA': 0,
    'CAPACITACION SANTA MARTA': 19, 'CAPACITACION CIENAGA': 19, 'CAPACITACION FUNDACION': 19, 'CAPACITACION PIVIJAY': 19,
    'INST. FORMACION TECNICO': 0, 'INST. FORMACION TECN CIENAGA': 0, 'INST. FORMACION TECN FUNDACION': 0, 'INST. FORMACION TECNICO PIVIJA': 0,
    'CAP ESCUELA MUSICAL SANTA MARTA': 19, 'BIBLIOTECA SANTA MTA': 19, 'UNIDAD DE CULTURA Y COMUNICACION': 19, 'TEATRO CAJAMAG': 0,
    'RECREACION. STA MTA': 19, 'RECREACION CIENAGA': 19, 'RECREACION FUNDAC.': 19, 'CENTRO RECREC.TEYUNA': 19, 'CAFETERIA TEYUNA': 8,
    'DEPORTES STA MTA': 19, 'DEPORTES CIENAGA': 19, 'DEPORTES FUNDACION .': 19, 'RECREACION PIVIJAY': 19,
    'CENTRO RECREACIONAL CIENAGA': 19, 'CENTRO RECREACIONAL FUNDACION': 19,
    'TURISMO SOCIAL STA MARTA': 19, 'TURISMO SOCIAL CIENAGA': 19, 'TURISMO SOCIAL FUNDACION': 19, 'TURISMO SOCIAL PIVIJAY': 19,
}
def _norm_serv_oficial(s):
    s = (s or '').upper()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^A-Z0-9]', '', s)
    return s
_OFICIAL_NORM = {_norm_serv_oficial(k): k for k in IMPUESTO_OFICIAL}
_RECREACION_POR_ZONA = {'Santa Marta':'RECREACION. STA MTA','Ciénaga':'RECREACION CIENAGA','Fundación':'RECREACION FUNDAC.'}
_DEPORTES_POR_ZONA = {'Santa Marta':'DEPORTES STA MTA','Ciénaga':'DEPORTES CIENAGA','Fundación':'DEPORTES FUNDACION .'}
_CAPACITACION_POR_ZONA = {'Santa Marta':'CAPACITACION SANTA MARTA','Ciénaga':'CAPACITACION CIENAGA','Fundación':'CAPACITACION FUNDACION'}
_IFT_POR_ZONA = {'Santa Marta':'INST. FORMACION TECNICO','IFT':'INST. FORMACION TECNICO','Ciénaga':'INST. FORMACION TECN CIENAGA','Fundación':'INST. FORMACION TECN FUNDACION'}
_TURISMO_POR_ZONA = {'Santa Marta':'TURISMO SOCIAL STA MARTA','Ciénaga':'TURISMO SOCIAL CIENAGA','Fundación':'TURISMO SOCIAL FUNDACION'}
def _por_zona_serv(mapa, zona):
    return mapa.get(zona) or mapa['Santa Marta']
_SERVICIO_RAW_FIJO = {
    'TEATRO CULPA':'TEATRO CAJAMAG','TEATRO- LOS DE LA CULPA':'TEATRO CAJAMAG','TEATRO CAJAMAG CULPA':'TEATRO CAJAMAG',
    'BOLETAS TEATRO ORQUESTA':'TEATRO CAJAMAG','BOLETA TEATRO ORQUETA ARANGO':'TEATRO CAJAMAG','boleta teatro orquesta':'TEATRO CAJAMAG',
    'TEATRO BOLETAS ORQUETAS':'TEATRO CAJAMAG','ENTRADAS ORQUESTA ARAGON':'TEATRO CAJAMAG','ENTRADAS TEATRO ORQUESTA ARAGON':'TEATRO CAJAMAG',
    'Teatro':'TEATRO CAJAMAG', 'Biblioteca':'BIBLIOTECA SANTA MTA',
    'Vacunación':'VACUNACION SANTA MARTA','VACUNA HEPATITIS A':'VACUNACION SANTA MARTA','VACUNA HEPATITIS B':'VACUNACION SANTA MARTA',
    'VACUNA MENINGOCOCO':'VACUNACION SANTA MARTA','HEPATITIS B PLENA':'VACUNACION SANTA MARTA','TETANO PLENA':'VACUNACION SANTA MARTA',
    'SERVICIOS UIS CIENAGA':'CAPACITACION CIENAGA','SERVICIOS UIS FUNDACION':'CAPACITACION FUNDACION',
}
for _k in ['CURSO DE NATACION ADULTO INICIO','CURSO DE NATACION INICIO ADULTOS','CURSO DE NATACION INICIACION','ALQUILER DE CANCHA','Deporte']:
    _SERVICIO_RAW_FIJO[_k] = '__DEPORTES_ZONA__'
for _k in ['CARIBE AVENTURA NIÑO','CARIBE AVENTURA ADULTO','CARIBE AVENTURA PASADIA','CUPO ADULTO CARIBE AVENTURA','NOCHE BLANCA KATAMARAN',
           'PASADIA ACUARIO','CAMINATA ECOLOGICA','CAMINATA ECOLOGICA INCA','PARQUE INFLAMBLE','PARQUE TEMATICO INFLABLE','CHIVA RUMBERA',
           'tradición de Cuba','SALIDAS PEDAGÓGICAS','ALQUILER DE SALON','ALQUILER DE AUDITORIO','ALQUILER DE SLAON X 4 HORAS','Alquiler de salones','Recreación']:
    _SERVICIO_RAW_FIJO[_k] = '__RECREACION_ZONA__'
for _k in ['PLAN DECAMERON NIÑO','PLAN DECAMERON ADULTO','PLAN TURISTICO CARTAGENA','PASADIA BARRANQUILLA','SEGURO DE VIDA']:
    _SERVICIO_RAW_FIJO[_k] = '__TURISMO_ZONA__'
for _k in ['IFT','Inscripción','Inglés conversacional']:
    _SERVICIO_RAW_FIJO[_k] = '__IFT_ZONA__'
for _k in ['CINEMARK','BOLETAS CINEMARK','COMBO CINE','combo de cine mark','combo cine','BONOS CINEMARK','ENTRADAS A CINEMARK','combo cine mark',
           'BONOS DE CINEMARK','combo de cine','BONOS PARA CINEMARK','Combo de cine mark','boletas cinemark','BOLETA CINEMARK','BONO CINEMARK','Bono Cinemark',
           'cinemark','CIBNEMARK','ENTRADAS A CINEMAK','combo de cinemark','comvo de cine mark','combo de cinemak','CINEMARK2','CINE COMBO',
           'boleta cine','BOLETAS DE CINE','Boleta de cine','ENTREDA CINEMAKR','ENTRADAS CINEMARK','ENTRADAS CINEMAKR','ENTRADA CINEMARK','bono de cinemark',
           'Combo de cine']:
    _SERVICIO_RAW_FIJO[_k] = '__RECREACION_ZONA__'
_TEYUNA_CAFE_KEYWORDS = ['aliment','bebida','cafeteria','gaseosa','almuerzo','refrigerio','perro caliente','parrillada','botellon','mesero']
for _k in ['ALIMENTOS Y BEBIDAS TEYUNA','BOTELLON DE AGUA','GASEOSA','ALMUERZO INFANTIL','ALMUERZO PARRILLADA ADULTOS','REGRIGERIO PERRO CALIENTE RANCHERO','MESERO']:
    _SERVICIO_RAW_FIJO[_k] = 'CAFETERIA TEYUNA'
for _k in ['Teyuna','ALOJAMIENTO Y EVENTOS TEYUNA','Paasadia a teyuna','ALQUILER DE KIOSKI','KIOSCO X 8 HORAS','SALON PARA CAPACITACION TEYUNA']:
    _SERVICIO_RAW_FIJO[_k] = '__TEYUNA_KEYWORD__'

def _resolver_servicio_oficial(t):
    raw = t.get('servicio')
    nrm = _norm_serv_oficial(raw)
    if nrm in _OFICIAL_NORM:
        return _OFICIAL_NORM[nrm]
    marker = _SERVICIO_RAW_FIJO.get(raw)
    if marker and not marker.startswith('__'):
        return marker
    zona = t.get('zona') or 'Santa Marta'
    if marker == '__DEPORTES_ZONA__': return _por_zona_serv(_DEPORTES_POR_ZONA, zona)
    if marker == '__RECREACION_ZONA__': return _por_zona_serv(_RECREACION_POR_ZONA, zona)
    if marker == '__TURISMO_ZONA__': return _por_zona_serv(_TURISMO_POR_ZONA, zona)
    if marker == '__IFT_ZONA__': return _por_zona_serv(_IFT_POR_ZONA, zona)
    if marker == '__TEYUNA_KEYWORD__':
        d = (t.get('detalle') or '').lower()
        return 'CAFETERIA TEYUNA' if any(kw in d for kw in _TEYUNA_CAFE_KEYWORDS) else 'CENTRO RECREC.TEYUNA'
    return 'Sin clasificar (revisar)'

def _servicio_agg(tx_list):
    agg = {}
    for t in tx_list:
        cat = _resolver_servicio_oficial(t)
        v = t.get('valor') or 0.0
        d = agg.setdefault(cat, {'servicio': cat, 'valor': 0.0, 'cantidad': 0})
        d['valor'] += v
        d['cantidad'] += 1
    rows = sorted(agg.values(), key=lambda r: -r['valor'])
    top = rows[:8]
    otros = rows[8:]
    if otros:
        top.append({'servicio':'Otros', 'valor': sum(r['valor'] for r in otros), 'cantidad': sum(r['cantidad'] for r in otros)})
    return top

all_tx = DATA['ventas']['transacciones']
ventas_servicio_by_period = {}
for ym_k in TVDATA['meses']:
    ventas_servicio_by_period[ym_k] = _servicio_agg([t for t in all_tx if t.get('ym')==ym_k])
ventas_servicio_by_period['acumulado'] = _servicio_agg(all_tx)
TVDATA['ventas_servicio_by_period'] = ventas_servicio_by_period

# ---- Corte del periodo (fecha "hasta" que se muestra en el encabezado del TV) ----
# Se corrige aqui SIEMPRE porque quedaba desactualizado corrida tras corrida
# (bug detectado repetidamente: 18-ago, 20-ago, 21-ago) al no tocarse este campo.
TVDATA.setdefault('periodo', {})['corte'] = TODAY.isoformat()

new_tv_json = json.dumps(TVDATA, ensure_ascii=False, separators=(',',':'))
tv_html = open(TV_MASTER, encoding='utf-8').read()
i = tv_html.index('window.TVDATA'); i2 = tv_html.index('=', i) + 1
s = tv_html[i2:]; lead_ws = len(s) - len(s.lstrip()); start = i2 + lead_ws
depth, end = 0, None
for idx in range(start, len(tv_html)):
    ch = tv_html[idx]
    if ch == '{': depth += 1
    elif ch == '}':
        depth -= 1
        if depth == 0:
            end = idx + 1; break
tv_html2 = tv_html[:start] + new_tv_json + tv_html[end:]
# El encabezado visible ("El asesor frente a su meta · corte YYYY-MM-DD") es un
# literal HTML separado del JSON de arriba, asi que hay que corregirlo tambien.
tv_html2 = re.sub(r'(El asesor frente a su meta · corte )\d{4}-\d{2}-\d{2}',
                   r'\g<1>' + TODAY.isoformat(), tv_html2)
open(TV_MASTER, 'w', encoding='utf-8').write(tv_html2)
print('TV master actualizado:', TV_MASTER, '| corte:', TODAY.isoformat())

with open(f'{AUTO}/last_run_summary.txt', 'w', encoding='utf-8') as f:
    f.write(f"Ultima corrida: {datetime.now().isoformat()}\n")
    f.write(f"Mes: {YM} | ventas nuevas: {len(new_tx)} (${month_total:,.0f}) | gestiones nuevas: {len(new_raw_gestiones)}\n")

print('=== PIPELINE MAESTRO COMPLETO ===')
