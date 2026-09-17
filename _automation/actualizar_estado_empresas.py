"""
actualizar_estado_empresas.py — Corrige el 'estado de congelamiento' de
DATA['empresas_full'] (campos per/fue/ue) usando TODAS las gestiones
registradas en DATA['gestiones']['raw_gestiones'] (que sí se actualiza en
cada corrida del pipeline), en vez de depender solo del export COMPANY de
Bitrix (que se congela hasta la próxima vez que alguien lo descargue).

Bug que corrige: una empresa puede tener gestiones reales este mes (o en
meses anteriores del contrato actual) pero seguir marcada en empresas_full
como 'No contactada' o 'Contactada - solo contrato anterior' porque esa
gestión ocurrió DESPUÉS del último export COMPANY que se cargó. Esto hace
que la empresa siga apareciendo en "top oportunidades de primer contacto"
y que los conteos de Gestionó/Sin gestión/Pendientes no cuadren con la
realidad.

Regla de corrección (conservadora, solo promueve, nunca degrada):
  - Si una empresa tiene AL MENOS UNA fila en raw_gestiones (osea, se
    gestionó en algún momento durante el contrato actual, que es el único
    periodo que cubre el reporte de Gestiones CER), su 'per' pasa a
    'Contactada - contrato actual', sin importar lo que dijera antes
    ('No contactada' o 'Contactada - solo contrato anterior').
  - 'fue' (fecha última gestión) se actualiza a la fecha más reciente
    encontrada en raw_gestiones para ese NIT, si es más reciente que la que
    ya tenía.
  - 'ue' (último evento) se actualiza al texto de gestión de esa fila más
    reciente.

USO:
    python actualizar_estado_empresas.py
"""
import glob, os, sys, json
from collections import Counter

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


def main():
    html = open(MASTER, encoding='utf-8').read()
    d_start = html.index('const DATA = ') + len('const DATA = ')
    d_end = html.index('function fmt(n)')
    blob = html[d_start:d_end].rstrip()
    assert blob.endswith(';')
    data = json.loads(blob[:-1])

    ef = data['empresas_full']
    raw = data['gestiones']['raw_gestiones']

    # Ultima gestion (fecha + texto) por NIT, tomando la mas reciente.
    ultima_por_nit = {}
    for r in raw:
        nit = r.get('nit')
        if not nit:
            continue
        if nit not in ultima_por_nit or r['fecha'] > ultima_por_nit[nit]['fecha']:
            ultima_por_nit[nit] = r

    changed_per = 0
    changed_fue = 0
    before_counts = Counter(e.get('per') or 'Sin dato' for e in ef)
    for e in ef:
        nit = e.get('nit')
        if not nit or nit not in ultima_por_nit:
            continue
        last = ultima_por_nit[nit]
        if e.get('per') != 'Contactada - contrato actual':
            e['per'] = 'Contactada - contrato actual'
            changed_per += 1
        if not e.get('fue') or last['fecha'] > e['fue']:
            e['fue'] = last['fecha']
            e['ue'] = last.get('gestion')
            changed_fue += 1
    after_counts = Counter(e.get('per') or 'Sin dato' for e in ef)

    data['empresas_agg']['per_counts'] = dict(after_counts)

    print(f"Empresas con 'per' promovido a 'Contactada - contrato actual': {changed_per}")
    print(f"Empresas con 'fue'/'ue' refrescado: {changed_fue}")
    print("Antes:", dict(before_counts))
    print("Después:", dict(after_counts))

    new_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    html2 = html[:d_start] + new_json + ';\n' + html[d_end:]
    open(MASTER, 'w', encoding='utf-8').write(html2)
    print(f"Guardado en {MASTER}")


if __name__ == '__main__':
    main()
