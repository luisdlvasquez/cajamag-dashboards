"""
build_tv.py — Vuelca el TVDATA recien recalculado (TV_Master_DATA.html) sobre
la copia real y desplegada del Tablero TV (Tablero_TV_Asesores_CER.html), que
a diferencia de Operativo/Gerencial NO se regenera desde cero: ya trae todo
su HTML/CSS/JS fijo, solo cambia el bloque `window.TVDATA = {...};`.

USO:
    python build_tv.py
"""
import glob, os, sys, re

_env_base = os.environ.get("PIPELINE_BASE_DIR")
if _env_base:
    AUTO = f"{_env_base}/_automation"
    TV_MASTER = f"{AUTO}/TV_Master_DATA.html"
    SRC_TV = f"{_env_base}/Tablero_TV_Asesores_CER.html"
    OUT = f"{os.environ.get('PIPELINE_OUT_DIR', _env_base + '/_out')}/Tablero_TV_Asesores_CER.html"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
else:
    _candidates = glob.glob("/sessions/*/mnt/Trabajando Juntos")
    if not _candidates:
        print("ERROR: no se encontro la carpeta 'Trabajando Juntos' montada bajo /sessions/*/mnt/")
        sys.exit(1)
    _mnt = os.path.dirname(_candidates[0])
    BASE = f"{_candidates[0]}/CAJAMAG/02_DASHBOARDS"
    AUTO = f"{BASE}/_automation"
    TV_MASTER = f"{AUTO}/TV_Master_DATA.html"
    SRC_TV = f"{BASE}/Tablero_TV_Asesores_CER.html"
    OUT = f"{_mnt}/outputs/Tablero_TV_Asesores_CER.html"


def find_blob_bounds(html, key_pattern):
    """Encuentra los limites {..} de un valor JSON dentro del HTML, contando
    llaves/corchetes con cuidado de comillas escapadas. (Copiado de
    recompute_tv_empresas.py para no depender de un import cruzado.)"""
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
    tv_master_html = open(TV_MASTER, encoding='utf-8').read()
    ms, me = find_blob_bounds(tv_master_html, r'window\.TVDATA\s*=\s*(\{)')
    new_blob = tv_master_html[ms:me]

    tv_html = open(SRC_TV, encoding='utf-8').read()
    s, e = find_blob_bounds(tv_html, r'window\.TVDATA\s*=\s*(\{)')
    tv_html2 = tv_html[:s] + new_blob + tv_html[e:]

    open(OUT, 'w', encoding='utf-8').write(tv_html2)
    print(f"Tablero TV actualizado -> {OUT} ({len(new_blob)} bytes de TVDATA)")


if __name__ == '__main__':
    main()
