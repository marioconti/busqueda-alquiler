"""Barrido de listados. Es el UNICO script que toca la red (junto con detalle.py).

Etiqueta (seccion 11 del perfil): pausa de 3 a 5 segundos, User-Agent normal, dos
corridas por dia como maximo. Si empiezan a volver 403 -> bajar la frecuencia y avisar.
NO se rotan proxies ni se evaden bloqueos: esto es una busqueda personal.

CUANTO TOLERA EL PORTAL *(medido 2026-08-21)*: contesto 403 en el pedido ~100 de una
corrida con pausa de 2-3 s, sin ningun bug de por medio. De ahi salen el presupuesto de
90 pedidos por corrida y la pausa de 3-5 s del config.

Sin dependencias externas: urllib de la biblioteca estandar.

*(Verificado 2026-08-14: el listado devuelve 200 con urllib pelado, 30 avisos por pagina,
y trae la descripcion completa de cada uno. No hace falta navegador headless.)*

COMO PAGINA
-----------
Pagina 1:  {tipo}-alquiler-{barrio}[-{filtro}]-orden-{orden}.html
Pagina N:  ... -pagina-{N}.html

Cuantas paginas hay se lee del propio listado (`listStore.paging.totalPages`), asi que no
se piden paginas de mas ni se cortan busquedas por la mitad.

DECISIONES DE BUSQUEDA (vienen de conocimiento/zonaprop.md)
-----------------------------------------------------------
- `casa-` EN SINGULAR: el plural devuelve solo casas; el singular incluye PH. Casi todos
  los buenos hallazgos salieron del singular.
- DOS PASADAS, no una: novedades por `-orden-publicado-descendente` y cobertura por
  ambientes con `-orden-precio-ascendente`. El porque esta en plan_de_barrido(), y es la
  correccion mas importante que tuvo este modulo: con una sola pasada por precio se pedia
  todos los dias el mismo conjunto.
- SIN filtro de fecha: esconde inventario vigente.
- SIN tag `-con-terraza`: ignora el barrio (probado, trajo Montevideo y Mar del Plata).
"""

from __future__ import annotations

import gzip
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import RAIZ, es_gba, load_config, zonas_a_barrer  # noqa: E402

DIR_CRUDO = RAIZ / "data" / "raw"
BASE = "https://www.zonaprop.com.ar"


class PortalCortado(Exception):
    """El portal devolvio 403/429. Bajar la frecuencia y avisar, no insistir."""


def slug(txt: str) -> str:
    t = unicodedata.normalize("NFKD", txt.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def url_zonaprop(tipo: str, barrio: str, pagina: int = 1,
                 filtro: str | None = None, orden: str = "precio-ascendente") -> str:
    """Arma la URL de un listado.

    DONDE VA CADA COSA — no es intercambiable, verificado contra los propios links del
    portal el 2026-08-21:

        {tipo}-alquiler-{tag}-{barrio}-{filtro}-orden-{orden}.html
                        ^^^^^          ^^^^^^^^
                    tag ANTES        filtro DESPUES

        departamentos-alquiler-saavedra-3-ambientes-orden-precio-ascendente.html
        departamentos-alquiler-saavedra-orden-publicado-descendente.html

    `tipo` puede traer un tag con '+' ("departamentos+con-terraza"). El unico tag que se
    probo -con-terraza- IGNORABA EL BARRIO y trajo departamentos de Montevideo y Punta
    Carretas: el soporte queda, el uso no.

    `orden` util: `precio-ascendente` (lo barato primero, para cubrir) y
    `publicado-descendente` (lo nuevo primero, para enterarse).
    """
    if "+" in tipo:
        tipo, tag = tipo.split("+", 1)
        base = f"{BASE}/{tipo}-alquiler-{tag}-{slug(barrio)}"
    else:
        base = f"{BASE}/{tipo}-alquiler-{slug(barrio)}"
    if filtro:
        base += f"-{filtro}"
    base += f"-orden-{orden}"
    return f"{base}.html" if pagina <= 1 else f"{base}-pagina-{pagina}.html"


# --------------------------------------------------------------------------- descarga

def bajar(url: str, cfg: dict) -> str:
    rl = cfg["rate_limit"]
    req = urllib.request.Request(url, headers={
        "User-Agent": rl["user_agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9",
        "Accept-Encoding": "gzip",
        "Connection": "close",
    })
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            crudo = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                crudo = gzip.decompress(crudo)
            return crudo.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise PortalCortado(f"{url} devolvio {e.code}: bajar la frecuencia y avisar") from e
        raise


def dormir(cfg: dict) -> None:
    rl = cfg["rate_limit"]
    time.sleep(random.uniform(float(rl["pausa_segundos_min"]), float(rl["pausa_segundos_max"])))


# --------------------------------------------------------------------------- plan

def plan_de_barrido(barrios: list[str], tipos: list[str], cfg: dict) -> list[dict]:
    """Que URLs se piden y en que orden. Es LA decision de este modulo.

    POR QUE HAY DOS PASADAS
    -----------------------
    Hasta el 2026-08-21 el barrido era uno solo: `-orden-precio-ascendente`, las N
    primeras paginas de cada barrio. Eso pide TODOS LOS DIAS EXACTAMENTE EL MISMO
    CONJUNTO -las N paginas mas baratas- y por eso Mario veia siempre lo mismo. Un aviso
    nuevo no entra arriba: entra en el medio de la lista, en la posicion que le toca por
    precio. Un 3 ambientes publicado hoy en Palermo a USD 1.400 cae cerca de la pagina 40
    de 107 y no lo veiamos nunca.

    Medido el 2026-08-21: 855 departamentos bajados de un universo de 6.991 en las 9
    zonas (12%), y ese 12% eran los mas baratos de cada barrio, o sea monoambientes:
    solo 43 tenian 2 dormitorios y 3 ambientes.

      1. NOVEDADES  -orden-publicado-descendente, pocas paginas.
         Es la unica pasada que trae algo distinto cada dia: lo recien publicado esta
         arriba por definicion. Verificado: respeta el barrio.

      2. COBERTURA  filtro de ambientes en el portal + precio ascendente, hasta el final.
         Con `-3-ambientes` Palermo pasa de 3.185 avisos (107 paginas) a 599 (20), y ahi
         el universo relevante SI se cubre entero. Ordenado por precio ascendente ya no
         trae monoambientes: trae los 3 ambientes mas baratos, que es lo que se busca.

    FILTROS DEL PORTAL, PROBADOS UNO POR UNO EL 2026-08-21
    ------------------------------------------------------
      -3-ambientes / -4-ambientes / -mas-de-5-ambientes   FILTRAN DE VERDAD. Se usan.
      -mas-de-2-ambientes    MIENTE: es ">=2", devuelve avisos de 2 ambientes. No sirve
                             para el minimo de 3 del perfil.
      -menos-de-2000-dolares NO FILTRA NADA: Saavedra devolvio 158 de 158 y el primero
                             era de USD 8.000. Descartado. El presupuesto se aplica de
                             nuestro lado, como duro.
    """
    b = cfg.get("busqueda", {}) or {}
    pag_nov = int(b.get("paginas_novedades", 2))
    tope = int(b.get("max_paginas_por_barrio", 12))
    slots = b.get("slots_ambientes") or ["3-ambientes", "4-ambientes", "mas-de-5-ambientes"]

    tareas: list[dict] = []
    # Primero TODAS las novedades de todos los barrios: si el presupuesto de pedidos
    # corta la corrida, lo que no puede faltar es lo nuevo.
    for tipo in tipos:
        for barrio in barrios:
            tareas.append({"tipo": tipo, "barrio": barrio, "filtro": None,
                           "orden": "publicado-descendente", "tope": pag_nov,
                           "pasada": "novedades"})
    # LA COBERTURA ROTA, Y HASTA EL 2026-08-31 ROTABA EN LA DIMENSION EQUIVOCADA.
    #
    # La rotacion nacio del 403 del 2026-08-21: si el orden es fijo, un corte por
    # presupuesto castiga siempre a los mismos. La idea era correcta y la implementacion
    # solo giraba los BARRIOS, dejando `for tipo: for slot:` fijos por fuera. O sea que
    # el giro reordenaba DENTRO de cada bloque de 9 y nunca cambiaba que bloque iba
    # primero. Medido el 2026-08-31 sobre el plan real de 72 tareas:
    #
    #     #0  casa/novedades      #18 casa/3-amb    #36 casa/mas-de-5
    #     #9  deptos/novedades    #27 casa/4-amb    #45 DEPTOS/3-amb
    #                                               #54 DEPTOS/4-amb
    #                                               #63 DEPTOS/mas-de-5
    #
    # Con 90 pedidos la corrida muere cerca de la tarea 40-50. Resultado: la cobertura de
    # DEPARTAMENTOS -que es el 95% del inventario de CABA, 2.846 deptos contra 160 casas-
    # arrancaba recien en la #45, y las de 4 y de mas-de-5 ambientes NO SE BAJARON NUNCA,
    # ni un solo dia. Confirmado en data/raw: 24 archivos de cobertura de deptos el 29
    # (la unica corrida que gasto el presupuesto entero) y CERO el 27, 28, 30 y 31.
    #
    # El arreglo son tres lineas y ninguna toca el presupuesto:
    #   1. `tipo` pasa a ser el bucle MAS INTERNO, asi casa y departamentos van pegados y
    #      un corte los parte por la mitad a los dos en vez de decapitar a uno.
    #   2. los SLOTS tambien giran por dia: sin eso `mas-de-5-ambientes` queda ultimo
    #      siempre, que es el mismo problema una dimension mas adentro.
    #   3. los barrios siguen girando como antes.
    hoy_ord = date.today().toordinal()
    giro_b = hoy_ord % max(1, len(barrios))
    giro_s = hoy_ord % max(1, len(slots))
    rotados = barrios[giro_b:] + barrios[:giro_b]
    slots_rot = slots[giro_s:] + slots[:giro_s]
    for slot in slots_rot:
        for barrio in rotados:
            for tipo in tipos:
                tareas.append({"tipo": tipo, "barrio": barrio, "filtro": slot,
                               "orden": "precio-ascendente", "tope": tope,
                               "pasada": f"cobertura/{slot}"})
    return tareas


# --------------------------------------------------------------------------- barrido

def _barrio_coincide(avisos: list[dict], barrio: str) -> bool:
    """EL CANARIO, ahora sobre lo que YA se bajo en vez de un pedido aparte.

    Dos veces en dos dias una URL mal armada devolvio 200 con contenido plausible: una
    lista YAML partida trajo toda CABA (403), y un tag mal ubicado trajo 810
    departamentos de Montevideo y Punta Carretas. La leccion quedo escrita -"el canario
    tiene que mirar QUE volvio, no cuanto"- pero costaba un pedido extra por tipo y solo
    miraba la primera combinacion. Mirando la pagina 1 de cada tarea sale gratis y cubre
    todas.
    """
    vistos = [slug(a.get("barrio") or "") for a in avisos if a.get("barrio")]
    if not vistos:
        return True  # sin dato de barrio no se puede desmentir; el filtro duro lo agarra

    # EN GBA SE PIDE EL PARTIDO Y VUELVEN SUS LOCALIDADES, asi que exigir el mismo nombre
    # da un falso positivo: se pide `san-isidro` y vuelve Martinez, que es la respuesta
    # CORRECTA. El 2026-08-24 esto dio por muerta la URL de casas de Vicente Lopez —una
    # que estaba verificada a mano— y abandono la cobertura entera de casas en GBA.
    # El canario sigue siendo un canario: comprueba que la geografia sea la pedida, solo
    # que en GBA "la pedida" es el partido, no una localidad.
    if es_gba(barrio):
        return sum(1 for a in avisos if es_gba(a.get("barrio"))) >= max(1, len(vistos) // 4)

    esperado = slug(barrio)
    return sum(1 for v in vistos if v == esperado) >= max(1, len(vistos) // 4)


def correr(barrios: list[str] | None = None, tipos: list[str] | None = None,
           max_paginas: int | None = None, verbose: bool = True,
           solo_pasada: str | None = None) -> dict:
    """Baja los listados segun plan_de_barrido(). Devuelve {etiqueta: ruta_al_html}."""
    import parse  # se importa aca para leer totalPages sin acoplar los modulos

    cfg = load_config()
    hoy = date.today().isoformat()
    barrios = [b for b in (barrios or zonas_a_barrer(cfg)) if len(slug(b)) >= 3]
    tipos = tipos or cfg.get("busqueda", {}).get("tipos_slug", ["casa"])
    presupuesto = int(cfg.get("busqueda", {}).get("max_requests_por_corrida", 200))

    tareas = plan_de_barrido(barrios, tipos, cfg)
    if solo_pasada:
        tareas = [t for t in tareas if t["pasada"].startswith(solo_pasada)]
    if max_paginas:
        for t in tareas:
            t["tope"] = min(t["tope"], max_paginas)

    bajados: dict[str, str] = {}
    muertas: set[tuple] = set()      # (tipo, filtro, orden) que el portal no respeta
    pedidos = 0
    por_pasada: dict[str, int] = {}
    cortado = False

    for t in tareas:
        forma = (t["tipo"], t["filtro"], t["orden"])
        if forma in muertas or cortado:
            continue
        pagina, total_paginas, avisos_tarea = 1, 1, 0

        while pagina <= min(total_paginas, t["tope"]):
            if pedidos >= presupuesto:
                print(f"  !  presupuesto de {presupuesto} pedidos agotado. "
                      f"Lo que falta se baja en la proxima corrida.")
                cortado = True
                break

            sufijo = f'{t["tipo"]}{"-" + t["filtro"] if t["filtro"] else ""}-{t["orden"][:4]}'
            etiqueta = f'zonaprop/{slug(t["barrio"])}/{sufijo}-p{pagina}'
            destino = DIR_CRUDO / hoy / (etiqueta.replace("/", "__") + ".html")
            destino.parent.mkdir(parents=True, exist_ok=True)

            if destino.exists() and destino.stat().st_size > 5000:
                html = destino.read_text(encoding="utf-8", errors="replace")
            else:
                try:
                    html = bajar(url_zonaprop(t["tipo"], t["barrio"], pagina,
                                              t["filtro"], t["orden"]), cfg)
                except PortalCortado as e:
                    print(f"  !! {e}")
                    return bajados
                except Exception as e:  # noqa: BLE001
                    print(f"  !  {etiqueta}: {type(e).__name__} {str(e)[:80]}")
                    dormir(cfg)
                    break
                pedidos += 1
                destino.write_text(html, encoding="utf-8")
                dormir(cfg)

            avisos, paging = parse.parsear_listado(html, t["barrio"])

            if pagina == 1:
                if not _barrio_coincide(avisos, t["barrio"]):
                    print(f'  !  {t["tipo"]}/{t["filtro"] or "sin filtro"}: la URL NO respeta '
                          f'el barrio (se pidio {t["barrio"]!r}). Se abandona esa forma de URL.')
                    destino.unlink(missing_ok=True)
                    muertas.add(forma)
                    break
                total_paginas = int(paging.get("totalPages") or 1)
                # Un total de paginas absurdo es un sintoma, no un dato: 1.501 paginas de
                # un barrio de CABA no existe. Si el portal dice eso, la URL esta mal.
                if total_paginas > 200:
                    print(f'  !  {etiqueta}: {total_paginas} paginas es imposible para un '
                          f'barrio. URL sospechosa, se abandona esa forma.')
                    muertas.add(forma)
                    break
                # SOLO EN COBERTURA. En novedades tomar 2 de 108 paginas es el DISENO
                # -lo recien publicado esta arriba por definicion, las otras 106 son
                # historia-, asi que el cartel salia para casi todos los barrios grandes
                # todos los dias y se leia como "no puede paginar". Mario lo reporto asi.
                # Una advertencia que se enciende siempre deja de ser una advertencia, y
                # ademas tapa la unica que importa: en cobertura, truncar SI es inventario
                # que no se mira.
                if total_paginas > t["tope"] and t["pasada"].startswith("cobertura"):
                    print(f'  !  {t["barrio"]}/{sufijo}: {total_paginas} paginas, se toman '
                          f'{t["tope"]}. El resto queda para las proximas corridas.')

            bajados[etiqueta] = str(destino)
            avisos_tarea += len(avisos)
            if not avisos:
                break
            pagina += 1

        if avisos_tarea:
            por_pasada[t["pasada"]] = por_pasada.get(t["pasada"], 0) + avisos_tarea
            if verbose:
                print(f'  {t["barrio"]:16s} {t["pasada"]:22s} {avisos_tarea:4d} avisos '
                      f'en {pagina - 1} pagina(s)')

    if verbose:
        print(f"\n  {pedidos} pedidos al portal - {len(bajados)} paginas")
        for p, n in sorted(por_pasada.items()):
            print(f"    {p:24s} {n:5d} avisos (con repetidos entre pasadas)")
        # QUE NO SE PIDIO. Que una corrida corte por presupuesto es lo normal -el plan
        # entero no entra en 90 pedidos, por eso rota-, pero callarlo hace que "corto por
        # presupuesto" y "no habia nada nuevo" se lean igual en pantalla.
        pedidas = {(t["tipo"], t["filtro"], t["barrio"]) for t in tareas
                   if (t["tipo"], t["filtro"], t["orden"]) not in muertas}
        faltan = len(tareas) - len([1 for t in tareas if any(
            k2.startswith(f'zonaprop/{slug(t["barrio"])}/{t["tipo"]}'
                          f'{"-" + t["filtro"] if t["filtro"] else ""}-{t["orden"][:4]}-p')
            for k2 in bajados)])
        if faltan > 0:
            print(f"    quedaron {faltan} de {len(tareas)} tareas sin pedir; las toma la "
                  f"proxima corrida (el orden gira todos los dias)")

    return bajados


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pasada = None
    if "--novedades" in sys.argv:
        pasada = "novedades"
    elif "--cobertura" in sys.argv:
        pasada = "cobertura"
    r = correr(args or None, solo_pasada=pasada)
    print(f"\n{len(r)} pagina(s) guardada(s) en {DIR_CRUDO}")
