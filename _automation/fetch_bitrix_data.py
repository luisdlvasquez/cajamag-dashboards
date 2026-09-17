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
from datetime import date, timedelta
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
_desde = os.environ.get('FECHA_DESDE') or f'{YM}-01'
_hasta = os.environ.get('FECHA_HASTA') or TODAY.isoformat()
FECHA_DESDE = _desde
FECHA_HASTA = _hasta

print(f'Rango de consulta: {FECHA_DESDE} -> {FECHA_HASTA} (YM={YM})')

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
    out = []
    start = 0
    while True:
        params = {'start': start}
        for k, v in (filter_ or {}).items():
            params[f'filter[{k}]'] = v
        for i, s in enumerate(select or []):
            params[f'select[{i}]'] = s
        for k, v in (order or {}).items():
            params[f'order[{k}]'] = v
        r = call(method, params)
        out.extend(r['result'])
        nxt = r.get('next')
        if nxt is None:
            break
        start = nxt
    return out


def batch(calls_dict):
    """calls_dict: {clave: 'metodo?param=valor&...'} (max 50 por tanda)."""
    out = {}
    items = list(calls_dict.items())
    for i in range(0, len(items), 50):
        chunk = dict(items[i:i + 50])
        r = call('batch', {'halt': 0, **{f'cmd[{k}]': v for k, v in chunk.items()}})
        out.update(r['result']['result'])
    return out


def _norm_txt(s):
    if not s:
        return ''
    s = s.upper()
    for a, b in [('Á', 'A'), ('É', 'E'), ('Í', 'I'), ('Ó', 'O'), ('Ú', 'U'), ('Ñ', 'N')]:
        s = s.replace(a, b)
    return s


def fecha_iso_a_ddmmyyyy(s):
    if not s:
        return ''
    # Bitrix devuelve '2026-09-16T00:00:00-05:00' o '2026-09-16'
    d = s[:10]
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

def resolve_users(user_ids):
    faltan = [u for u in set(user_ids) if u and u not in USER_NAME_CACHE]
    for i in range(0, len(faltan), 50):
        chunk = faltan[i:i + 50]
        cmds = {f'u{j}': f'user.get?ID={uid}' for j, uid in enumerate(chunk)}
        r = call('batch', {'halt': 0, **{f'cmd[{k}]': v for k, v in cmds.items()}})
        for j, uid in enumerate(chunk):
            data = r['result']['result'].get(f'u{j}') or []
            if data:
                u = data[0]
                USER_NAME_CACHE[uid] = f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip()
            else:
                USER_NAME_CACHE[uid] = ''

def resolve_contacts(contact_ids):
    faltan = [c for c in set(contact_ids) if c and c != '0' and c not in CONTACT_CACHE]
    for i in range(0, len(faltan), 50):
        chunk = faltan[i:i + 50]
        cmds = {f'c{j}': f'crm.contact.get?ID={cid}' for j, cid in enumerate(chunk)}
        r = call('batch', {'halt': 0, **{f'cmd[{k}]': v for k, v in cmds.items()}})
        for j, cid in enumerate(chunk):
            CONTACT_CACHE[cid] = r['result']['result'].get(f'c{j}') or {}

def resolve_companies(company_ids):
    faltan = [c for c in set(company_ids) if c and c != '0' and c not in COMPANY_CACHE]
    for i in range(0, len(faltan), 50):
        chunk = faltan[i:i + 50]
        cmds = {f'e{j}': f'crm.company.get?ID={cid}' for j, cid in enumerate(chunk)}
        r = call('batch', {'halt': 0, **{f'cmd[{k}]': v for k, v in cmds.items()}})
        for j, cid in enumerate(chunk):
            COMPANY_CACHE[cid] = r['result']['result'].get(f'e{j}') or {}

CONTACT_CACHE = {}
COMPANY_CACHE = {}

def resolve_productrows(deal_ids):
    out = {}
    ids = list(deal_ids)
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        cmds = {f'p{j}': f'crm.deal.productrows.get?id={did}' for j, did in enumerate(chunk)}
        r = call('batch', {'halt': 0, **{f'cmd[{k}]': v for k, v in cmds.items()}})
        for j, did in enumerate(chunk):
            out[did] = r['result']['result'].get(f'p{j}') or []
    return out


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

def fetch_ventas(category_id, tipo_venta, etapa_ok_name, fname):
    print(f'Consultando ventas categoria {category_id} ({tipo_venta})...')
    stage_id = None
    r = call('crm.dealcategory.stage.list', {'id': category_id})
    STAGE_NAME_CACHE[str(category_id)] = {s['STATUS_ID']: s['NAME'] for s in r['result']}
    for status_id, name in STAGE_NAME_CACHE[str(category_id)].items():
        if _norm_txt(name) == _norm_txt(etapa_ok_name):
            stage_id = status_id
            break
    if stage_id is None:
        raise RuntimeError(f'No se encontro la etapa "{etapa_ok_name}" en categoria {category_id}')

    deals = list_all('crm.deal.list', filter_={
        'CATEGORY_ID': category_id,
        'STAGE_ID': stage_id,
        '>=UF_CRM_1681152455392': FECHA_DESDE,
        '<=UF_CRM_1681152455392': FECHA_HASTA,
    }, select=['ID', 'TITLE', 'ASSIGNED_BY_ID', 'CONTACT_ID', 'COMPANY_ID', 'OPPORTUNITY',
               'UF_CRM_1681152455392', 'UF_CRM_1681146110054', 'UF_CRM_1681146530307'])
    print(f'  {len(deals)} negocios en etapa "{etapa_ok_name}" con Fecha de facturacion en rango.')
    if not deals:
        return pd.DataFrame()

    deal_ids = [d['ID'] for d in deals]
    resolve_users([d.get('ASSIGNED_BY_ID') for d in deals])
    resolve_contacts([d.get('CONTACT_ID') for d in deals])
    resolve_companies([d.get('COMPANY_ID') for d in deals])
    productrows = resolve_productrows(deal_ids)

    rows = []
    for d in deals:
        contact = CONTACT_CACHE.get(d.get('CONTACT_ID')) or {}
        company = COMPANY_CACHE.get(d.get('COMPANY_ID')) or {}
        servicio_cotizar = ENUM_SERVICIOS_COTIZAR.get(str(d.get('UF_CRM_1681146530307') or ''), '')
        servicio_utilizar = ENUM_SERVICIOS_UTILIZAR.get(str(d.get('UF_CRM_1681146110054') or ''), '')
        categoria_afiliacion = ENUM_CATEGORIA_AFILIACION.get(str(contact.get('UF_CRM_1679886333416') or ''), '')
        nit = contact.get('UF_CRM_1756067100077') or company.get('UF_CRM_1679587096910') or ''
        base = {
            'ID': d['ID'],
            'Etapa de la negociación': etapa_ok_name,
            'Fecha de facturación': fecha_iso_a_ddmmyyyy(d.get('UF_CRM_1681152455392')),
            'Persona responsable': USER_NAME_CACHE.get(d.get('ASSIGNED_BY_ID'), ''),
            'Contacto: Nombre': contact.get('NAME') or '',
            'Contacto: Apellido': contact.get('LAST_NAME') or '',
            'Compañía: Nombre de la compañía': company.get('TITLE') or '',
            'Servicios a cotizar': servicio_cotizar,
            'Servicios a utilizar': servicio_utilizar,
            'Contacto: Categoría de afiliación': categoria_afiliacion,
            'Contacto: Nit empresa': nit,
            'Compañía: Nit': company.get('UF_CRM_1679587096910') or '',
        }
        lineas = productrows.get(d['ID']) or []
        if lineas:
            for ln in lineas:
                row = dict(base)
                row['Producto'] = ln.get('PRODUCT_NAME') or ''
                row['Precio'] = ln.get('PRICE')
                row['Cantidad'] = ln.get('QUANTITY')
                rows.append(row)
        else:
            row = dict(base)
            row['Producto'] = ''
            row['Precio'] = None
            row['Cantidad'] = None
            row['Ingreso'] = d.get('OPPORTUNITY')
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------- 2. GESTIONES (todas las categorias, ver docstring) ----------------

def fetch_gestiones(fname):
    print('Consultando gestiones (todas las categorias, campo Fecha y hora evento)...')
    deals = list_all('crm.deal.list', filter_={
        '>=UF_CRM_1740428746956': FECHA_DESDE,
        '<=UF_CRM_1740428746956': FECHA_HASTA,
    }, select=['ID', 'CATEGORY_ID', 'STAGE_ID', 'ASSIGNED_BY_ID', 'COMPANY_ID',
               'UF_CRM_1740428746956', 'UF_CRM_1740085404851', 'UF_CRM_1740428574274',
               'UF_CRM_1740429016'])
    print(f'  {len(deals)} negocios con Fecha y hora evento en rango (todas las categorias).')

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
            'Fecha y hora evento': fecha_iso_a_ddmmyyyy(d.get('UF_CRM_1740428746956')),
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
    df_ind = fetch_ventas(2, 'Individual', 'CERRADO GANADO', 'individual.xls')
    to_export_html(df_ind, os.path.join(OUT_DIR, 'individual.xls'))

    df_emp = fetch_ventas(1, 'Empresarial', 'CERRADO GANADO', 'empresarial.xls')
    to_export_html(df_emp, os.path.join(OUT_DIR, 'empresarial.xls'))

    df_ift = fetch_ventas(4, 'IFT', 'CERRADO MATRICULARO', 'ift.xls')
    to_export_html(df_ift, os.path.join(OUT_DIR, 'ift.xls'))

    df_gest = fetch_gestiones('gestiones.xls')
    to_export_html(df_gest, os.path.join(OUT_DIR, 'gestiones.xls'))

    print('Listo. Archivos generados en', OUT_DIR)
