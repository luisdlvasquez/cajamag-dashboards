"""
fetch_bitrix_data.py — Reemplaza el paso manual de "descargar 4 exports de Bitrix"
(individual.xls, empresarial.xls, ift.xls, gestiones.xls) por una consulta directa
a la API REST de Bitrix24. Genera los 4 archivos con EXACTAMENTE las mismas columnas
que pipeline_master.py ya espera (ver docstring de ese archivo), para no tener que
tocar ninguna de las reglas de negocio ya validadas ahi (metas prorateadas, filtro de
etapas, IVA, etc.) — solo se reemplaza el origen del dato, no la logica.

Hallazgos clave verificados en vivo contra Bitrix el 17-sep-2026 (no supuestos):

1. VENTAS (categorias 1=Empresarial, 2=Individual, 4=IFT): cada venta es un Negocio
   normal. Se filtra por la etapa "ganada" de cada categoria (CERRADO GANADO /
   CERRADO GANADO / CERRADO MATRICULARO) y por el campo "Fecha de facturacion"
   (UF_CRM_1681152455392) en el rango del mes en curso. Las lineas de producto salen
   de crm.deal.productrows.get (PRICE/QUANTITY/PRODUCT_NAME).

2. GESTIONES: cada gestion (llamada/visita/etc.) es su PROPIO Negocio (no un campo
   que se sobreescribe), con fecha real en UF_CRM_1740428746956 ("Fecha y hora
   evento"). La mayoria vive en la categoria 24 ("Promoción, Mantenimiento y
   Afiliaciones"), pero se confirmo que TAMBIEN aparecen gestiones registradas
   directamente sobre negocios de venta en curso (categorias 1 y 2) -- en
   septiembre-2026 hubo 2020 en cat.24, 100 en cat.2 y 24 en cat.1 (total 2144).
   Por eso esta consulta NO filtra por categoria: trae CUALQUIER negocio, de
   CUALQUIER categoria, que tenga ese campo de fecha poblado en el rango, igual que
   hace el reporte nativo "Gestiones CER" con Pipeline="Todos". Luego se aplica el
   mismo filtro de etapa que ya existia en pipeline_master.py (ETAPAS_OK =
   {'EJECUCION EVENTO','CERRADO GANADO','CERRADO PERDIDO'}), resolviendo el nombre
   de la etapa segun la categoria de CADA negocio (porque STAGE_ID es un codigo
   especifico de cada categoria, ej. 'C24:UC_OCS434' = "Ejecución evento" en la
   categoria 24, pero ese mismo codigo no existe en la categoria 2).

3. Verificado tambien: un mismo negocio-gestion conserva su ID fijo mientras cambia
   de etapa (ej. 33051 paso de "Planificación evento" a "Ejecución evento" en 3
   segundos, mismo ID) -- por eso no hay riesgo de duplicado por cambio de etapa:
   cada corrida reconstruye el mes completo desde cero (nunca acumula), asi que un
   negocio que cambio de etapa varias veces antes de asentarse solo aparece una vez,
   con su etapa final.

USO:
  BITRIX_REST_URL=https://.../rest/xxx/yyy/ \
  BITRIX_EXPORT_DIR=/ruta/a/Downloads \
  FECHA_DESDE=2026-09-01 FECHA_HASTA=2026-09-17 \
  python3 fetch_bitrix_data.py

Si no se definen FECHA_DESDE/FECHA_HASTA, se usa el mes en curso completo (dia 1
hasta hoy), calculado con la MISMA regla de "mes en curso" que pipeline_master.py
(ver effective_today en ese archivo -- congelado hasta el dia 7 del mes siguiente).
"""
import os, sys, json, time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import urllib.request
import urllib.parse

import pandas as pd

BITRIX_BASE = os.environ.get('BITRIX_REST_URL')
if not BITRIX_BASE:
    print('ERROR: falta la variable de entorno BITRIX_REST_URL (webhook de Bitrix). '
          'Por seguridad esta URL (incluye un token) NUNCA debe quedar escrita en el '
          'codigo -- debe venir siempre de un secret (GitHub Actions: Settings > '
          'Secrets and variables > Actions > BITRIX_REST_URL).')
    sys.exit(1)
if not BITRIX_BASE.endswith('/'):
    BITRIX_BASE += '/'
OUT_DIR = os.environ.get('BITRIX_EXPORT_DIR')
if not OUT_DIR:
    import glob
    _candidates = glob.glob("/sessions/*/mnt/Downloads") or glob.glob("/sessions/*/mnt/Trabajando Juntos/../Downloads")
    OUT_DIR = _candidates[0] if _candidates else "./_bitrix_export"
os.makedirs(OUT_DIR, exist_ok=True)


def effective_today(real_today=None):
    """MISMA regla que pipeline_master.py (actualizada 17-sep-2026 a pedido de
    Luis): el mes se congela (deja de ser 'mes en curso') recien DESPUES del dia 7
    del mes siguiente, para dar margen a que se terminen de cargar/ajustar ventas y
    gestiones del mes que cierra. Del dia 1 al 7 del mes nuevo, el pipeline sigue
    tratando el mes ANTERIOR como 'mes en curso'."""
    t = real_today or date.today()
    if t.day <= 7:
        first_of_month = t.replace(day=1)
        return first_of_month - timedelta(days=1)
    return t


_FORCE_TODAY = os.environ.get('FORCE_TODAY')
TODAY = date.fromisoformat(_FORCE_TODAY) if _FORCE_TODAY else effective_today()
YM = TODAY.strftime('%Y-%m')
def _ultimo_dia_mes(d):
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


# 29-sep-2026: por defecto se consulta el MES COMPLETO (dia 1 al ultimo dia), no
# "hasta hoy". Antes, una venta ganada cuya Fecha de facturacion quedaba
# registrada un dia posterior a hoy (o el mismo dia, segun como Bitrix compare
# la hora) no entraba hasta ese dia -- y Operaciones si la cuenta. El pipeline
# de todos modos solo toma lo que cae dentro del mes en curso.
_desde = os.environ.get('FECHA_DESDE') or f'{YM}-01'
_hasta = os.environ.get('FECHA_HASTA') or _ultimo_dia_mes(TODAY).isoformat()
FECHA_DESDE = _desde
FECHA_HASTA = _hasta
# Ventana de consulta a la API ampliada 3 dias a cada lado: el filtro de fechas de
# Bitrix compara contra fecha-hora y puede correr el limite por zona horaria (un
# negocio con fecha 01/09 puede quedar "antes" de '2026-09-01' en el servidor --
# sospecha principal del caso del negocio 30843 de sep-2026). Despues se filtra
# localmente por la fecha tal como la muestra Bitrix.
CONSULTA_DESDE = (date.fromisoformat(FECHA_DESDE) - timedelta(days=3)).isoformat()
CONSULTA_HASTA = (date.fromisoformat(FECHA_HASTA) + timedelta(days=3)).isoformat()

print(f'Rango de negocio: {FECHA_DESDE} -> {FECHA_HASTA} (YM={YM}); '
      f'consulta API ampliada {CONSULTA_DESDE} -> {CONSULTA_HASTA}')


TZ_COLOMBIA = timezone(timedelta(hours=-5))  # Colombia no tiene horario de verano


def _fecha_local(s):
    """Fecha calendario de un campo tipo FECHA de Bitrix (Fecha de facturacion,
    fecha de cierre), tal como la ve el usuario en la interfaz.

    CAUSA RAIZ del reclamo de Operaciones (29-sep-2026: Karen Cantillo -$245.000,
    Martha Lorena Celedon -$436.000, y antes el negocio 30843 de Maria Jose):
    Bitrix guarda algunas de estas fechas como medianoche UTC y la API las
    devuelve convertidas a la hora del usuario del webhook. Un negocio que en
    Bitrix dice "01/09/2026" llega como '2026-08-31T19:00:00-05:00'. Antes se
    tomaban los primeros 10 caracteres ('2026-08-31') y la venta caia en agosto
    (mes ya cerrado) -> no se contaba en ningun mes. Otras fechas si llegan como
    '2026-09-01T00:00:00-05:00'. Solucion: pasar a hora Colombia y redondear a la
    medianoche mas cercana (19:00 del dia anterior -> dia siguiente; 00:00 ->
    mismo dia). Funciona sin importar en que zona horaria guarde el servidor."""
    if not s:
        return ''
    s = str(s)
    if 'T' not in s:
        return s[:10]
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return s[:10]
    if dt.tzinfo is not None:
        dt = dt.astimezone(TZ_COLOMBIA)
    d = dt.date()
    if dt.hour >= 12:
        d = d + timedelta(days=1)
    return d.isoformat()


def _fecha_hora_local(s):
    """Dia de un campo FECHA-HORA real (ej. 'Fecha y hora evento' de gestiones,
    DATE_CREATE), en hora Colombia, sin redondeo."""
    if not s:
        return ''
    s = str(s)
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(TZ_COLOMBIA)
        return dt.date().isoformat()
    except ValueError:
        return s[:10]


def _en_rango(s):
    f = _fecha_local(s)
    return bool(f) and FECHA_DESDE <= f <= FECHA_HASTA

# ---------------- helpers REST ----------------

def _http_get(url):
    for intento in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            if intento == 4:
                raise
            time.sleep(1.5 * (intento + 1))


def call(method, params=None):
    qs = urllib.parse.urlencode(params or {}, doseq=True)
    url = f'{BITRIX_BASE}{method}.json' + (f'?{qs}' if qs else '')
    r = _http_get(url)
    if 'error' in r:
        raise RuntimeError(f'{method} -> {r}')
    return r


def list_all(method, filter_=None, select=None, order=None):
    """Pagina TODO el resultado. 29-sep-2026: se fuerza orden estable por ID
    (sin 'order' Bitrix no garantiza el mismo orden entre paginas y la
    paginacion por 'start' puede saltarse o repetir registros) y se deduplica
    por ID."""
    out = []
    vistos = set()
    start = 0
    if not order:
        order = {'ID': 'ASC'}
    while True:
        params = {'start': start}
        for k, v in (filter_ or {}).items():
            if isinstance(v, (list, tuple)):
                params[f'filter[{k}][]'] = list(v)
            else:
                params[f'filter[{k}]'] = v
        for i, s in enumerate(select or []):
            params[f'select[{i}]'] = s
        for k, v in (order or {}).items():
            params[f'order[{k}]'] = v
        r = call(method, params)
        for item in r['result']:
            iid = item.get('ID') if isinstance(item, dict) else None
            if iid is not None:
                if iid in vistos:
                    continue
                vistos.add(iid)
            out.append(item)
        nxt = r.get('next')
        if nxt is None:
            break
        start = nxt
    return out


BATCH_FALLIDOS = []  # sub-llamadas que fallaron incluso tras reintentos (se reportan en el cuadre)


def batch(calls_dict):
    """Ejecuta {clave: 'metodo?params'} en tandas de 50 y REINTENTA las
    sub-llamadas que fallen (result_error, p.ej. QUERY_LIMIT_EXCEEDED). Hasta el
    29-sep-2026 una sub-llamada fallida devolvia vacio en silencio (el negocio
    quedaba sin lineas de producto o sin nombre de asesor/contacto)."""
    out = {}
    pendientes = dict(calls_dict)
    for intento in range(4):
        if not pendientes:
            break
        items = list(pendientes.items())
        fallidos = {}
        for i in range(0, len(items), 50):
            chunk = dict(items[i:i + 50])
            r = call('batch', {'halt': 0, **{f'cmd[{k}]': v for k, v in chunk.items()}})
            res = r['result'].get('result') or {}
            errs = r['result'].get('result_error') or {}
            if not isinstance(res, dict):
                res = {}
            if not isinstance(errs, dict):
                errs = {}
            for k, v in chunk.items():
                if k in errs or k not in res:
                    fallidos[k] = v
                else:
                    out[k] = res[k]
        pendientes = fallidos
        if pendientes:
            time.sleep(2 * (intento + 1))
    if pendientes:
        print(f'  ADVERTENCIA: {len(pendientes)} sub-llamadas batch fallaron tras 4 intentos')
        BATCH_FALLIDOS.extend(pendientes.values())
    return out


def _norm_txt(s):
    if not s:
        return ''
    s = s.upper()
    for a, b in [('Á', 'A'), ('É', 'E'), ('Í', 'I'), ('Ó', 'O'), ('Ú', 'U'), ('Ñ', 'N')]:
        s = s.replace(a, b)
    return s


def fecha_iso_a_ddmmyyyy(s, es_fecha_hora=False):
    """ISO de Bitrix -> 'dd/mm/aaaa'. Para campos FECHA usa _fecha_local (con la
    correccion de zona horaria); para campos FECHA-HORA usa el dia en hora
    Colombia."""
    if not s:
        return ''
    d = _fecha_hora_local(s) if es_fecha_hora else _fecha_local(s)
    y, m, day = d.split('-')
    return f'{day}/{m}/{y}'


# ---------------- caches de metadata ----------------

print('Cargando metadata de campos y usuarios...')
DEAL_FIELDS = call('crm.deal.fields')['result']
CONTACT_FIELDS = call('crm.contact.fields')['result']
COMPANY_FIELDS = call('crm.company.fields')['result']

def _enum_map(fields_dict, code):
    items = fields_dict.get(code, {}).get('items', [])
    return {str(it['ID']): it['VALUE'] for it in items}

ENUM_SERVICIOS_UTILIZAR = _enum_map(DEAL_FIELDS, 'UF_CRM_1681146110054')
ENUM_SERVICIOS_COTIZAR = _enum_map(DEAL_FIELDS, 'UF_CRM_1681146530307')
ENUM_TIPO_ACTIVIDAD = _enum_map(DEAL_FIELDS, 'UF_CRM_1740085404851')
ENUM_TIPO_EVENTO = _enum_map(DEAL_FIELDS, 'UF_CRM_1740428574274')
ENUM_CATEGORIA_AFILIACION = _enum_map(CONTACT_FIELDS, 'UF_CRM_1679886333416')

STAGE_NAME_CACHE = {}  # category_id -> {STATUS_ID: NAME}

def stage_name(category_id, stage_id):
    cid = str(category_id)
    if cid not in STAGE_NAME_CACHE:
        r = call('crm.dealcategory.stage.list', {'id': cid})
        STAGE_NAME_CACHE[cid] = {s['STATUS_ID']: s['NAME'] for s in r['result']}
    return STAGE_NAME_CACHE[cid].get(stage_id, stage_id)

CATEGORY_NAME_CACHE = None

def category_name(category_id):
    global CATEGORY_NAME_CACHE
    if CATEGORY_NAME_CACHE is None:
        r = call('crm.dealcategory.list')
        CATEGORY_NAME_CACHE = {str(c['ID']): c['NAME'] for c in r['result']}
    return CATEGORY_NAME_CACHE.get(str(category_id), str(category_id))

USER_NAME_CACHE = {}
CONTACT_CACHE = {}
COMPANY_CACHE = {}


def resolve_users(user_ids):
    faltan = sorted({u for u in user_ids if u and u not in USER_NAME_CACHE})
    if not faltan:
        return
    res = batch({f'u{uid}': f'user.get?ID={uid}' for uid in faltan})
    for uid in faltan:
        data = res.get(f'u{uid}') or []
        if data:
            u = data[0]
            USER_NAME_CACHE[uid] = f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip()
        else:
            # No se pudo resolver: se deja el ID visible en vez de '' para que la
            # venta no quede "sin asesor" (y se note en el cuadre).
            USER_NAME_CACHE[uid] = f'(usuario Bitrix {uid})'


def resolve_contacts(contact_ids):
    faltan = sorted({c for c in contact_ids if c and c != '0' and c not in CONTACT_CACHE})
    if not faltan:
        return
    res = batch({f'c{cid}': f'crm.contact.get?ID={cid}' for cid in faltan})
    for cid in faltan:
        CONTACT_CACHE[cid] = res.get(f'c{cid}') or {}


def resolve_companies(company_ids):
    faltan = sorted({c for c in company_ids if c and c != '0' and c not in COMPANY_CACHE})
    if not faltan:
        return
    res = batch({f'e{cid}': f'crm.company.get?ID={cid}' for cid in faltan})
    for cid in faltan:
        COMPANY_CACHE[cid] = res.get(f'e{cid}') or {}


def resolve_productrows(deal_ids):
    """Devuelve {deal_id: [lineas]} SOLO para los negocios cuya consulta de
    productos respondio bien. Un negocio ausente del dict = no se pudo leer
    (distinto de "no tiene productos", que es una lista vacia)."""
    ids = list(deal_ids)
    if not ids:
        return {}
    res = batch({f'p{did}': f'crm.deal.productrows.get?id={did}' for did in ids})
    return {did: (res[f'p{did}'] or []) for did in ids if f'p{did}' in res}


def to_export_html(df, path):
    """Escribe un DataFrame como tabla HTML con meta charset utf-8 explicito --
    sin esto pandas/lxml mis-detectan la codificacion y se corrompen las tildes
    (bug ya encontrado y corregido una vez, ver ESTADO_DEL_PROYECTO.md)."""
    table_html = df.to_html(index=False, na_rep='')
    full = (
        '<!DOCTYPE html><html><head>'
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"></head>'
        f'<body>{table_html}</body></html>'
    )
    with open(path, 'w', encoding='utf-8') as f:
        f.write(full)
    print(f'  escrito {path} ({len(df)} filas)')


# ---------------- 1. VENTAS ----------------
#
# 29-sep-2026 (reclamo de Operaciones: Karen Cantillo -$245.000, Martha Lorena
# Celedon -$436.000 en Individual, total ~$1.067.800 de diferencia): ademas de
# traer las ventas, cada corrida ahora arma un CUADRE que deja por escrito, negocio
# por negocio, todo lo que podria explicar una diferencia contra lo que ve
# Operaciones en Bitrix:
#   - negocios ganados cuya Fecha de facturacion esta vacia o cae fuera del mes
#   - negocios con Fecha de facturacion en el mes en una etapa "exitosa" distinta
#     a la que cuenta el pipeline
#   - ventas ganadas en pipelines distintos a 1/2/4
#   - negocios cuyo valor por productos (Precio x Cantidad) no coincide con el
#     Ingreso (OPPORTUNITY) del negocio, o con productos en $0
#   - consultas a Bitrix que fallaron
# El cuadre se guarda en _automation/diag/cuadre_ventas.json y CUADRE_VENTAS.md
# (se versiona en el repo en cada corrida).

CATEGORIAS_VENTA = {
    '1': ('Empresarial', 'CERRADO GANADO'),
    '2': ('Individual', 'CERRADO GANADO'),
    '4': ('IFT', 'CERRADO MATRICULARO'),
}
CAMPO_FACT = 'UF_CRM_1681152455392'
SELECT_VENTA = ['ID', 'TITLE', 'CATEGORY_ID', 'STAGE_ID', 'STAGE_SEMANTIC_ID', 'ASSIGNED_BY_ID',
                'CONTACT_ID', 'COMPANY_ID', 'OPPORTUNITY', 'IS_MANUAL_OPPORTUNITY', 'CLOSEDATE',
                'DATE_MODIFY', 'DATE_CREATE', CAMPO_FACT, 'UF_CRM_1681146110054', 'UF_CRM_1681146530307']

CUADRE = {
    'generado_utc': None,
    'rango': None,
    'categorias': {},
    'fuera_por_fecha': [],       # ganados en cat. de venta, fecha fact. vacia o fuera del mes
    'otra_etapa_exitosa': [],    # fecha fact. en el mes, etapa exitosa distinta a la contada
    'otras_categorias': [],      # ganados con fecha fact. en el mes en pipelines != 1/2/4
    'valor_distinto': [],        # sum(lineas) != OPPORTUNITY
    'valor_por_ingreso': [],     # se uso OPPORTUNITY porque lineas en $0 o no se pudieron leer
    'cantidades_raras': [],      # cantidades sospechosas (ej. precio y cantidad invertidos)
    'no_ganados_del_mes': [],    # negocios creados/cerrados en el mes que NO estan en la etapa ganada
    'por_asesor': {},
    'batch_fallidos': 0,
    'batch_fallidos_detalle': [],
}


def _num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def _stages(category_id):
    cid = str(category_id)
    if cid not in STAGE_NAME_CACHE:
        r = call('crm.dealcategory.stage.list', {'id': cid})
        STAGE_NAME_CACHE[cid] = {s['STATUS_ID']: s['NAME'] for s in r['result']}
    return STAGE_NAME_CACHE[cid]


def _resumen_negocio(d, motivo=None, extra=None):
    r = {
        'id': d.get('ID'),
        'pipeline': category_name(d.get('CATEGORY_ID')),
        'etapa': stage_name(d.get('CATEGORY_ID'), d.get('STAGE_ID')),
        'asesor': USER_NAME_CACHE.get(d.get('ASSIGNED_BY_ID'), d.get('ASSIGNED_BY_ID')),
        'fecha_facturacion': _fecha_local(d.get(CAMPO_FACT)) or None,
        'fecha_cierre': _fecha_local(d.get('CLOSEDATE')) or None,
        'fecha_creacion': _fecha_hora_local(d.get('DATE_CREATE')) or None,
        'semantica': d.get('STAGE_SEMANTIC_ID'),
        'ingreso': _num(d.get('OPPORTUNITY')),
        'titulo': d.get('TITLE'),
    }
    if motivo:
        r['motivo'] = motivo
    if extra:
        r.update(extra)
    return r


def fetch_ventas(category_id, tipo_venta, etapa_ok_name):
    print(f'Consultando ventas categoria {category_id} ({tipo_venta})...')
    stages = _stages(category_id)
    stage_id = next((sid for sid, name in stages.items()
                     if _norm_txt(name).strip() == _norm_txt(etapa_ok_name)), None)
    if stage_id is None:
        raise RuntimeError(f'No se encontro la etapa "{etapa_ok_name}" en categoria {category_id}')

    candidatos = list_all('crm.deal.list', filter_={
        'CATEGORY_ID': category_id,
        'STAGE_ID': stage_id,
        f'>={CAMPO_FACT}': CONSULTA_DESDE,
        f'<={CAMPO_FACT}': CONSULTA_HASTA,
    }, select=SELECT_VENTA)
    deals = [d for d in candidatos if _en_rango(d.get(CAMPO_FACT))]
    print(f'  {len(deals)} negocios en "{etapa_ok_name}" con Fecha de facturacion '
          f'{FECHA_DESDE}..{FECHA_HASTA} (de {len(candidatos)} en la ventana ampliada).')

    # --- diagnostico: ganados de esta categoria cerrados/modificados en el mes que NO entraron
    contados = {d['ID'] for d in deals}
    ganados_mes = list_all('crm.deal.list', filter_={
        'CATEGORY_ID': category_id,
        'STAGE_SEMANTIC_ID': 'S',
        '>=DATE_MODIFY': CONSULTA_DESDE,
    }, select=SELECT_VENTA)
    # --- diagnostico: fecha de facturacion en el mes pero en otra etapa
    con_fecha_mes = list_all('crm.deal.list', filter_={
        'CATEGORY_ID': category_id,
        f'>={CAMPO_FACT}': CONSULTA_DESDE,
        f'<={CAMPO_FACT}': CONSULTA_HASTA,
        '!STAGE_ID': stage_id,
    }, select=SELECT_VENTA)

    # --- diagnostico: TODO negocio de la categoria creado o cerrado en el mes que no
    # quedo contado (cualquier etapa, abiertos y perdidos incluidos). Sirve para
    # cuadrar contra reportes de Operaciones que usan otro criterio (fecha de
    # cierre, pagos, etc.).
    movidos = list_all('crm.deal.list', filter_={
        'CATEGORY_ID': category_id,
        '>=DATE_MODIFY': CONSULTA_DESDE,
    }, select=SELECT_VENTA)

    resolve_users([d.get('ASSIGNED_BY_ID') for d in deals + ganados_mes + con_fecha_mes + movidos])


    for d in ganados_mes:
        if d['ID'] in contados:
            continue
        f = _fecha_local(d.get(CAMPO_FACT))
        cierre = _fecha_local(d.get('CLOSEDATE'))
        if f and _en_rango(d.get(CAMPO_FACT)):
            continue  # la cubre el bloque 'otra etapa' de abajo
        if not f and not (cierre and FECHA_DESDE <= cierre <= FECHA_HASTA):
            continue  # ganado viejo que solo se edito este mes
        if f and not (cierre and FECHA_DESDE <= cierre <= FECHA_HASTA):
            continue  # facturado en otro mes y cerrado en otro mes: no es de este mes
        CUADRE['fuera_por_fecha'].append(_resumen_negocio(
            d, 'Fecha de facturacion vacia' if not f else f'Fecha de facturacion {f} fuera del mes (cerrado {cierre})'))

    etapas_otras = Counter()
    for d in con_fecha_mes:
        if not _en_rango(d.get(CAMPO_FACT)):
            continue
        nombre = stage_name(d.get('CATEGORY_ID'), d.get('STAGE_ID'))
        etapas_otras[nombre] += 1
        if d.get('STAGE_SEMANTIC_ID') == 'S':
            CUADRE['otra_etapa_exitosa'].append(_resumen_negocio(d, f'Etapa "{nombre}" (no es "{etapa_ok_name}")'))

    ya_listados = {x['id'] for k in ('fuera_por_fecha', 'otra_etapa_exitosa') for x in CUADRE[k]}
    for d in movidos:
        if d['ID'] in contados or d['ID'] in ya_listados:
            continue
        creado = _fecha_hora_local(d.get('DATE_CREATE'))
        cierre = _fecha_local(d.get('CLOSEDATE'))
        en_mes = lambda x: bool(x) and FECHA_DESDE <= x <= FECHA_HASTA
        if not (en_mes(creado) or (d.get('STAGE_SEMANTIC_ID') != 'P' and en_mes(cierre))):
            continue
        if _num(d.get('OPPORTUNITY')) <= 0:
            continue
        CUADRE['no_ganados_del_mes'].append(_resumen_negocio(d, 'No esta en la etapa ganada'))

    CUADRE['categorias'][str(category_id)] = {
        'tipo_venta': tipo_venta,
        'etapa_contada': etapa_ok_name,
        'negocios_contados': len(deals),
        'otras_etapas_con_fecha_en_el_mes': dict(etapas_otras),
    }
    if not deals:
        return pd.DataFrame()

    deal_ids = [d['ID'] for d in deals]
    resolve_contacts([d.get('CONTACT_ID') for d in deals])
    resolve_companies([d.get('COMPANY_ID') for d in deals])
    productrows = resolve_productrows(deal_ids)

    rows = []
    suma_lineas_cat = 0.0
    suma_ingreso_cat = 0.0
    for d in deals:
        contact = CONTACT_CACHE.get(d.get('CONTACT_ID')) or {}
        company = COMPANY_CACHE.get(d.get('COMPANY_ID')) or {}
        servicio_cotizar = ENUM_SERVICIOS_COTIZAR.get(str(d.get('UF_CRM_1681146530307') or ''), '')
        servicio_utilizar = ENUM_SERVICIOS_UTILIZAR.get(str(d.get('UF_CRM_1681146110054') or ''), '')
        categoria_afiliacion = ENUM_CATEGORIA_AFILIACION.get(str(contact.get('UF_CRM_1679886333416') or ''), '')
        nit = contact.get('UF_CRM_1756067100077') or company.get('UF_CRM_1679587096910') or ''
        asesor = USER_NAME_CACHE.get(d.get('ASSIGNED_BY_ID'), '')
        ingreso = _num(d.get('OPPORTUNITY'))
        base = {
            'ID': d['ID'],
            'Etapa de la negociación': etapa_ok_name,
            'Fecha de facturación': fecha_iso_a_ddmmyyyy(d.get(CAMPO_FACT)),
            'Persona responsable': asesor,
            'Contacto: Nombre': contact.get('NAME') or '',
            'Contacto: Apellido': contact.get('LAST_NAME') or '',
            'Compañía: Nombre de la compañía': company.get('TITLE') or '',
            'Servicios a cotizar': servicio_cotizar,
            'Servicios a utilizar': servicio_utilizar,
            'Contacto: Categoría de afiliación': categoria_afiliacion,
            'Contacto: Nit empresa': nit,
            'Compañía: Nit': company.get('UF_CRM_1679587096910') or '',
        }
        lineas = productrows.get(d['ID'])
        suma_lineas = sum(_num(ln.get('PRICE')) * _num(ln.get('QUANTITY')) for ln in (lineas or []))
        for ln in (lineas or []):
            q = _num(ln.get('QUANTITY'))
            if q > 100 or (0 < _num(ln.get('PRICE')) < 100):
                CUADRE['cantidades_raras'].append(_resumen_negocio(d, 'Precio/cantidad sospechosos', {
                    'producto': ln.get('PRODUCT_NAME'), 'precio': _num(ln.get('PRICE')), 'cantidad': q}))

        usar_ingreso = False
        if lineas is None:
            usar_ingreso = True
            motivo = 'No se pudieron leer los productos del negocio (error de Bitrix); se uso el Ingreso'
        elif lineas and suma_lineas <= 0 and ingreso > 0:
            usar_ingreso = True
            motivo = 'Productos con valor $0; se uso el Ingreso del negocio'
        if usar_ingreso:
            CUADRE['valor_por_ingreso'].append(_resumen_negocio(d, motivo, {'valor_productos': suma_lineas}))
        elif lineas and abs(suma_lineas - ingreso) > 1:
            CUADRE['valor_distinto'].append(_resumen_negocio(d, 'Precio x Cantidad de productos != Ingreso del negocio', {
                'valor_productos': suma_lineas, 'diferencia': round(ingreso - suma_lineas, 2),
                'ingreso_manual': d.get('IS_MANUAL_OPPORTUNITY')}))

        if lineas and not usar_ingreso:
            valor_contado = suma_lineas
            for ln in lineas:
                row = dict(base)
                row['Producto'] = ln.get('PRODUCT_NAME') or ''
                row['Precio'] = ln.get('PRICE')
                row['Cantidad'] = ln.get('QUANTITY')
                rows.append(row)
        else:
            valor_contado = ingreso
            row = dict(base)
            row['Producto'] = ''
            row['Precio'] = None
            row['Cantidad'] = None
            row['Ingreso'] = d.get('OPPORTUNITY')
            rows.append(row)

        suma_lineas_cat += valor_contado
        suma_ingreso_cat += ingreso
        pa = CUADRE['por_asesor'].setdefault(asesor or '(sin asesor)', {})
        k = pa.setdefault(tipo_venta, {'negocios': 0, 'valor_contado': 0.0, 'ingreso_bitrix': 0.0})
        k['negocios'] += 1
        k['valor_contado'] += valor_contado
        k['ingreso_bitrix'] += ingreso

    CUADRE['categorias'][str(category_id)].update({
        'valor_contado': round(suma_lineas_cat, 2),
        'ingreso_bitrix_de_esos_negocios': round(suma_ingreso_cat, 2),
    })
    return pd.DataFrame(rows)


def fetch_otras_categorias():
    """Ventas ganadas (etapa exitosa) con Fecha de facturacion en el mes que viven
    en pipelines distintos a 1/2/4 -- no se cuentan, pero se reportan."""
    deals = list_all('crm.deal.list', filter_={
        '!CATEGORY_ID': list(CATEGORIAS_VENTA.keys()),
        'STAGE_SEMANTIC_ID': 'S',
        f'>={CAMPO_FACT}': CONSULTA_DESDE,
        f'<={CAMPO_FACT}': CONSULTA_HASTA,
    }, select=SELECT_VENTA)
    deals = [d for d in deals if _en_rango(d.get(CAMPO_FACT)) and str(d.get('CATEGORY_ID')) not in CATEGORIAS_VENTA]
    resolve_users([d.get('ASSIGNED_BY_ID') for d in deals])
    for d in deals:
        CUADRE['otras_categorias'].append(_resumen_negocio(d, 'Ganado en un pipeline que no es de ventas (1/2/4)'))


# Negocios puntuales a revisar en cada cuadre (ej. reclamos de Operaciones). Se
# pueden agregar mas IDs aqui o via la variable de entorno DIAG_DEAL_IDS="1,2,3".
DIAG_DEAL_IDS = ['30843']


def diagnosticar_negocios():
    ids = [x.strip() for x in (os.environ.get('DIAG_DEAL_IDS') or '').split(',') if x.strip()] or DIAG_DEAL_IDS
    res = batch({f'd{i}': f'crm.deal.get?id={i}' for i in ids})
    out = []
    for i in ids:
        d = res.get(f'd{i}')
        if not d:
            out.append({'id': i, 'motivo': 'No se pudo leer (no existe o sin permiso)'})
            continue
        resolve_users([d.get('ASSIGNED_BY_ID')])
        r = _resumen_negocio(d, 'Revision puntual', {
            'fecha_facturacion_cruda': d.get(CAMPO_FACT),
            'categoria_id': d.get('CATEGORY_ID'), 'stage_id': d.get('STAGE_ID'),
        })
        out.append(r)
    CUADRE['negocios_consultados'] = out


def escribir_cuadre():
    from datetime import datetime, timezone
    base_dir = os.environ.get('PIPELINE_BASE_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    diag_dir = os.path.join(base_dir, '_automation', 'diag')
    os.makedirs(diag_dir, exist_ok=True)
    CUADRE['generado_utc'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    CUADRE['rango'] = {'desde': FECHA_DESDE, 'hasta': FECHA_HASTA, 'ym': YM}
    CUADRE['batch_fallidos'] = len(BATCH_FALLIDOS)
    CUADRE['batch_fallidos_detalle'] = [c.split('?')[0] + '?' + c.split('?')[1][:40] for c in BATCH_FALLIDOS][:50]
    for a in CUADRE['por_asesor'].values():
        for k in a.values():
            k['valor_contado'] = round(k['valor_contado'], 2)
            k['ingreso_bitrix'] = round(k['ingreso_bitrix'], 2)
    with open(os.path.join(diag_dir, 'cuadre_ventas.json'), 'w', encoding='utf-8') as f:
        json.dump(CUADRE, f, ensure_ascii=False, indent=1)

    def money(v):
        return '$' + f'{v:,.0f}'.replace(',', '.')

    L = [f'# Cuadre de ventas {YM} (corrida {CUADRE["generado_utc"]})', '',
         f'Rango: {FECHA_DESDE} a {FECHA_HASTA}. Se cuentan los negocios en la etapa ganada de cada '
         'pipeline de ventas con Fecha de facturacion dentro del rango.', '']
    riesgo = [('fuera_por_fecha', 'Ganados en el mes con Fecha de facturacion vacia o de otro mes'),
              ('otra_etapa_exitosa', 'Facturados en el mes en otra etapa exitosa'),
              ('otras_categorias', 'Ganados en pipelines que no son de ventas'),
              ('valor_por_ingreso', 'Contados por Ingreso (productos en $0/ilegibles)'),
              ('valor_distinto', 'Productos != Ingreso')]
    L.append('## Alertas (lo primero que hay que revisar si Operaciones reporta diferencias)')
    hay = False
    for key, titulo in riesgo:
        items = CUADRE.get(key) or []
        if items:
            hay = True
            L.append(f"- **{titulo}: {len(items)} negocios, {money(sum(i.get('ingreso') or 0 for i in items))}**")
    if CUADRE['batch_fallidos']:
        hay = True
        L.append(f"- Consultas a Bitrix fallidas: {CUADRE['batch_fallidos']}")
    if not hay:
        L.append('- Sin alertas: todo negocio ganado del mes quedo contado.')
    posibles = {}
    for key in ('fuera_por_fecha', 'otra_etapa_exitosa', 'otras_categorias'):
        for it in CUADRE.get(key) or []:
            posibles[it['asesor']] = posibles.get(it['asesor'], 0) + (it.get('ingreso') or 0)
    if posibles:
        L.append('')
        L.append('Posibles ventas no contadas, por asesor (revisar con Operaciones):')
        for a, v in sorted(posibles.items(), key=lambda x: -x[1]):
            L.append(f'- {a}: {money(v)}')
    L.append('')
    L.append('## Totales contados por pipeline')
    for cid, c in CUADRE['categorias'].items():
        L.append(f"- {c['tipo_venta']} (pipeline {cid}, etapa {c['etapa_contada']}): "
                 f"{c['negocios_contados']} negocios, {money(c.get('valor_contado', 0))}")
    L.append('')
    L.append('## Por asesor (valor contado vs Ingreso en Bitrix de esos mismos negocios)')
    L.append('| Asesor | Tipo | Negocios | Contado | Ingreso Bitrix |')
    L.append('|---|---|---:|---:|---:|')
    for asesor in sorted(CUADRE['por_asesor']):
        for tipo, k in sorted(CUADRE['por_asesor'][asesor].items()):
            L.append(f"| {asesor} | {tipo} | {k['negocios']} | {money(k['valor_contado'])} | {money(k['ingreso_bitrix'])} |")
    secciones = [
        ('fuera_por_fecha', 'Ganados este mes que NO se cuentan por la Fecha de facturacion'),
        ('otra_etapa_exitosa', 'Con Fecha de facturacion en el mes pero en otra etapa exitosa'),
        ('otras_categorias', 'Ganados con Fecha de facturacion en el mes en otros pipelines'),
        ('valor_por_ingreso', 'Negocios contados por su Ingreso (productos en $0 o ilegibles)'),
        ('valor_distinto', 'Negocios donde Precio x Cantidad de productos no coincide con el Ingreso'),
        ('cantidades_raras', 'Lineas con precio/cantidad sospechosos'),
        ('no_ganados_del_mes', 'Negocios creados o cerrados en el mes que NO estan ganados (abiertos o perdidos, con valor)'),
        ('negocios_consultados', 'Revision puntual de negocios'),
    ]
    for key, titulo in secciones:
        items = CUADRE.get(key) or []
        L.append('')
        L.append(f'## {titulo} ({len(items)})')
        if not items:
            L.append('Ninguno.')
            continue
        L.append('| ID | Asesor | Pipeline | Etapa | F. creacion | F. facturacion | F. cierre | Ingreso | Detalle |')
        L.append('|---|---|---|---|---|---|---|---:|---|')
        for it in sorted(items, key=lambda x: (str(x.get('asesor')), str(x.get('id')))):
            det = it.get('motivo') or ''
            if 'valor_productos' in it:
                det += f" (productos {money(it['valor_productos'])})"
            if 'producto' in it:
                det += f" ({it['producto']}: precio {it['precio']}, cant. {it['cantidad']})"
            it = {**{'asesor': '-', 'pipeline': '-', 'etapa': '-', 'fecha_facturacion': None, 'fecha_cierre': None, 'ingreso': 0}, **it}
            if it.get('fecha_facturacion_cruda') is not None or 'stage_id' in it:
                det = (det + f" [cat {it.get('categoria_id')}, stage {it.get('stage_id')}, fact. cruda {it.get('fecha_facturacion_cruda')!r}]").strip()
            L.append(f"| {it['id']} | {it['asesor']} | {it['pipeline']} | {it['etapa']} | "
                     f"{it.get('fecha_creacion') or '-'} | {it['fecha_facturacion'] or '-'} | {it['fecha_cierre'] or '-'} | {money(it['ingreso'])} | {det} |")
    L.append('')
    L.append(f"Consultas a Bitrix que fallaron tras reintentos: {CUADRE['batch_fallidos']} "
             f"{CUADRE['batch_fallidos_detalle']}")
    with open(os.path.join(diag_dir, 'CUADRE_VENTAS.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    print(f'Cuadre escrito en {diag_dir} -- fuera_por_fecha={len(CUADRE["fuera_por_fecha"])}, '
          f'otra_etapa_exitosa={len(CUADRE["otra_etapa_exitosa"])}, otras_categorias={len(CUADRE["otras_categorias"])}, '
          f'valor_por_ingreso={len(CUADRE["valor_por_ingreso"])}, valor_distinto={len(CUADRE["valor_distinto"])}')


# ---------------- 2. GESTIONES (todas las categorias, ver docstring) ----------------

def fetch_gestiones(fname):
    print('Consultando gestiones (todas las categorias, campo Fecha y hora evento)...')
    # Gestiones: solo hasta HOY (son eventos ya sucedidos), aunque ventas mire el mes
    # completo. Misma ventana ampliada + filtro local que ventas (29-sep-2026).
    gest_hasta = os.environ.get('FECHA_HASTA') or min(TODAY, _ultimo_dia_mes(TODAY)).isoformat()
    candidatos = list_all('crm.deal.list', filter_={
        '>=UF_CRM_1740428746956': CONSULTA_DESDE,
        '<=UF_CRM_1740428746956': (date.fromisoformat(gest_hasta) + timedelta(days=3)).isoformat(),
    }, select=['ID', 'CATEGORY_ID', 'STAGE_ID', 'ASSIGNED_BY_ID', 'COMPANY_ID',
               'UF_CRM_1740428746956', 'UF_CRM_1740085404851', 'UF_CRM_1740428574274',
               'UF_CRM_1740429016'])
    deals = [d for d in candidatos
             if FECHA_DESDE <= _fecha_hora_local(d.get('UF_CRM_1740428746956')) <= gest_hasta]
    print(f'  {len(deals)} negocios con Fecha y hora evento {FECHA_DESDE}..{gest_hasta} (todas las categorias).')

    ETAPAS_OK = {'EJECUCION EVENTO', 'CERRADO GANADO', 'CERRADO PERDIDO'}
    filtrados = []
    excluidos = 0
    for d in deals:
        nombre_etapa = stage_name(d['CATEGORY_ID'], d['STAGE_ID'])
        if _norm_txt(nombre_etapa) not in ETAPAS_OK:
            excluidos += 1
            continue
        d['_etapa_nombre'] = nombre_etapa
        filtrados.append(d)
    print(f'  {len(filtrados)} en etapa valida (excluidas {excluidos} por planificacion/aplazado/etc.)')
    if not filtrados:
        return pd.DataFrame()

    resolve_users([d.get('ASSIGNED_BY_ID') for d in filtrados])
    resolve_companies([d.get('COMPANY_ID') for d in filtrados])

    rows = []
    for d in filtrados:
        company = COMPANY_CACHE.get(d.get('COMPANY_ID')) or {}
        tipo_actividad = ENUM_TIPO_ACTIVIDAD.get(str(d.get('UF_CRM_1740085404851') or ''), '')
        tipo_evento_ids = d.get('UF_CRM_1740428574274') or []
        if not isinstance(tipo_evento_ids, list):
            tipo_evento_ids = [tipo_evento_ids]
        tipo_evento = '/'.join(ENUM_TIPO_EVENTO.get(str(i), '') for i in tipo_evento_ids if i)
        rows.append({
            'Fecha y hora evento': fecha_iso_a_ddmmyyyy(d.get('UF_CRM_1740428746956'), es_fecha_hora=True),
            'Etapa de la negociación': d['_etapa_nombre'],
            'Persona responsable': USER_NAME_CACHE.get(d.get('ASSIGNED_BY_ID'), ''),
            'Compañía: Nombre de la compañía': company.get('TITLE') or '',
            'Compañía: Nit': company.get('UF_CRM_1679587096910') or '',
            'Tipo de actividad (V)': tipo_actividad,
            'Tipo de evento (V)': tipo_evento,
            'Descripción del evento (V)': d.get('UF_CRM_1740429016') or '',
            'Pipeline de la negociación': category_name(d['CATEGORY_ID']),
        })
    return pd.DataFrame(rows)


# ---------------- main ----------------

if __name__ == '__main__':
    df_ind = fetch_ventas(2, 'Individual', 'CERRADO GANADO')
    to_export_html(df_ind, os.path.join(OUT_DIR, 'individual.xls'))

    df_emp = fetch_ventas(1, 'Empresarial', 'CERRADO GANADO')
    to_export_html(df_emp, os.path.join(OUT_DIR, 'empresarial.xls'))

    df_ift = fetch_ventas(4, 'IFT', 'CERRADO MATRICULARO')
    to_export_html(df_ift, os.path.join(OUT_DIR, 'ift.xls'))

    try:
        fetch_otras_categorias()
    except Exception as e:  # el diagnostico nunca debe tumbar la actualizacion
        print('  (diagnostico otras categorias fallo:', e, ')')

    df_gest = fetch_gestiones('gestiones.xls')
    to_export_html(df_gest, os.path.join(OUT_DIR, 'gestiones.xls'))

    try:
        diagnosticar_negocios()
    except Exception as e:
        print('  (diagnostico de negocios puntuales fallo:', e, ')')

    try:
        escribir_cuadre()
    except Exception as e:
        print('  (no se pudo escribir el cuadre:', e, ')')

    print('Listo. Archivos generados en', OUT_DIR)
