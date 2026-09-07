"""Responde una sola pregunta: hace falta buscar, o los datos ya son de hoy.

Existe porque `abrir.bat` tenia que decidirlo y esa decision no se puede tomar en un
.bat: la fecha en batch depende del idioma de Windows (`%date%` devolvia "21-08-Fri" en
esta maquina) y leer JSON desde cmd es peor. El que sabe que dia es y donde esta el dato
es Python.

Uso:
    python scripts/estado.py --hay-que-buscar    -> codigo de salida 2 = si, 1 = no
    python scripts/estado.py                     -> lo imprime en castellano

El codigo de salida es lo que consume el .bat (`if errorlevel 2`). 0 no se usa a
proposito: en batch `errorlevel 0` es siempre verdadero y se presta a confusion.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import DIR_DATA, leer_json  # noqa: E402


def ultimo_barrido() -> str | None:
    """El dia en que se bajo algo del portal por ultima vez.

    NO es lo mismo que "cuando se genero la pagina": un rebuild sin red actualiza la
    pagina sin traer un solo aviso nuevo. Confundir las dos cosas es lo que hizo que el
    sistema pasara seis dias congelado sin que nadie lo notara.
    """
    doc = leer_json(DIR_DATA / "avisos.json", {})
    return (doc.get("meta") or {}).get("ultimo_barrido")


def dias_desde_barrido() -> int | None:
    d = ultimo_barrido()
    if not d:
        return None
    try:
        y, m, dd = (int(x) for x in str(d)[:10].split("-"))
    except ValueError:
        return None
    return (date.today() - date(y, m, dd)).days


def main() -> int:
    dias = dias_desde_barrido()
    hay_que_buscar = dias is None or dias >= 1

    if "--hay-que-buscar" in sys.argv:
        return 2 if hay_que_buscar else 1

    if dias is None:
        print("Nunca se busco en el portal.")
    elif dias == 0:
        print(f"Ya se busco hoy ({ultimo_barrido()}).")
    else:
        print(f"Ultima busqueda hace {dias} dia(s) ({ultimo_barrido()}).")
    return 2 if hay_que_buscar else 1


if __name__ == "__main__":
    sys.exit(main())
