"""
refrescar_empresas_bitrix.py -- 20-nov-2026 (a pedido de Luis).

Problema: DATA['empresas_full'] (asesor asignado 'ase', etc.) venia de un export de
Bitrix que se congelaba; las reasignaciones masivas de empresas entre asesores
(22-oct: 365, 3-nov: 416, 11-nov: 60 y las de cada dia) NO llegaban a los dashboards.

Solucion: en cada corrida se consulta crm.company.list (ASSIGNED_BY_ID + NIT) y se
actualiza 'ase' de cada empresa de empresas_full (cruce por NIT, solo digitos).
Es conservadora: si Bitrix falla, o cruza menos del 50 % de las empresas, no cambia nada.
"""
import os, re, json, time, urllib.request, urllib.parse, urllib.error

CAMPO_NIT = 'UF_CRM_1679587096910'
_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*'}


def _get(base, method, params):
    url = f'{base}{method}.json?' + urllib.parse.urlencode(params, doseq=True)
    for i in range(5):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception:
            if i == 4:
                raise
            time.sleep(1.5 * (i + 1))


def _digits(s):
    return re.sub(r'\D', '', str(s or ''))


def _nit_keys(s):
    d = _digits(s)
    ks = {d} if d else set()
    if len(d) > 9:          # NIT con digito de verificacion pegado
        ks.add(d[:-1])
    return ks


def aplicar(DATA):
    base = os.environ.get('BITRIX_REST_URL') or ''
    if not base:
        print('  [empresas] sin BITRIX_REST_URL: se omite el refresco de asignaciones')
        return 0
    if not base.endswith('/'):
        base += '/'
    try:
        companies, start = [], 0
        while True:
            params = {'start': start, 'order[ID]': 'ASC',
                      'select[0]': 'ID', 'select[1]': 'ASSIGNED_BY_ID', 'select[2]': CAMPO_NIT}
            r = _get(base, 'crm.company.list', params)
            companies += r.get('result') or []
            if r.get('next') is None:
                break
            start = r['next']
        uids = sorted({c.get('ASSIGNED_BY_ID') for c in companies if c.get('ASSIGNED_BY_ID')})
        nombres = {}
        for i in range(0, len(uids), 50):
            chunk = uids[i:i + 50]
            r = _get(base, 'batch', {'halt': 0, **{f'cmd[u{u}]': f'user.get?ID={u}' for u in chunk}})
            res = (r.get('result') or {}).get('result') or {}
            for u in chunk:
                d = res.get(f'u{u}') or []
                if d:
                    nombres[u] = f"{d[0].get('NAME', '')} {d[0].get('LAST_NAME', '')}".strip()
    except Exception as e:
        print(f'  [empresas] no se pudo consultar Bitrix ({e}); se conserva la asignacion anterior')
        return 0

    por_nit = {}
    for c in companies:
        nm = nombres.get(c.get('ASSIGNED_BY_ID'))
        if not nm:
            continue
        for k in _nit_keys(c.get(CAMPO_NIT)):
            por_nit.setdefault(k, nm)

    ef = DATA['empresas_full']
    cruzadas, cambios = 0, []
    for e in ef:
        nm = None
        for k in _nit_keys(e.get('nit')):
            if k in por_nit:
                nm = por_nit[k]
                break
        if nm is None:
            continue
        cruzadas += 1
        if e.get('ase') != nm:
            cambios.append((e, nm))
    print(f'  [empresas] Bitrix: {len(companies)} empresas; cruzadas con el dashboard: {cruzadas}/{len(ef)}')
    if cruzadas < 0.5 * len(ef):
        print('  [empresas] cruce < 50 %: se omite por seguridad (sin cambios)')
        return 0
    for e, nm in cambios:
        e['ase'] = nm
    print(f'  [empresas] asesor reasignado en {len(cambios)} empresas')
    return len(cambios)
