"""MercadoLibre: tercer portal. Devuelve avisos con el MISMO esquema que parse.py.

POR QUE ESTABA APAGADO Y POR QUE SE PRENDIO
-------------------------------------------
El sondeo del 2026-08-14 lo descarto con una sola medicion: `casas/alquiler/saavedra`
= 11 resultados. Era el PEOR caso posible para este portal — el barrio mas chico del
perfil y el tipo de propiedad que ML casi no publica — y encima se hizo antes de que
los departamentos entraran al perfil (eso fue la sesion 9).

Medido de nuevo el 2026-08-23 sobre departamentos y el corredor norte:

    Villa Urquiza 414 · Nunez 370 · Colegiales 165 · Saavedra 97 · Coghlan 63

1.109 departamentos. Dos ordenes de magnitud sobre la medicion vieja.

LO QUE ROBOTS.TXT PERMITE Y LO QUE NO  (leido entero, bloque `User-agent: *`)
-----------------------------------------------------------------------------
Esto MANDA sobre el diseno del barrido, no es un detalle:

    PERMITIDO   /departamentos/alquiler/capital-federal/<barrio>/
                /casas/alquiler/capital-federal/<barrio>/
                /ph/alquiler/capital-federal/<barrio>/
                /<tipo>/alquiler/mas-de-3-ambientes/capital-federal/<barrio>/

    PROHIBIDO   /*_Desde_          -> NO SE PUEDE PAGINAR
                /*_OrderId_        -> NO SE PUEDE ORDENAR (ni por fecha ni por precio)
                /*_PriceRange_     -> NO SE PUEDE FILTRAR POR PRECIO
                *_Cocheras_ *_Banos_ *_HAS*GRILL_ *_COVERED*AREA_ ...

Consecuencia directa: de cada busqueda se ve UNA pagina, 48 avisos, en el orden que
elige el portal. Por eso el barrido no pide paginas: pide CONSULTAS MAS ANGOSTAS.

    casas  -> 13 avisos en Villa Urquiza  -> entra entera en una pagina
    ph     -> 26 avisos                   -> entra entera
    deptos -> 414, con `mas-de-3-ambientes` bajan a 88 -> se ven 48

`mas-de-3-ambientes` SE VERIFICO MIRANDO LOS VALORES, no que devolviera 200: los 48
que vuelven son de 3, 4 y 5 ambientes. Es ">= 3", que es exactamente `ambientes_min`
del perfil. (En Zonaprop el analogo `-mas-de-2-ambientes` resulto ser ">= 2" y el
`-menos-de-2000-dolares` no filtraba nada: en este portal se comprueba igual.)

LIMITACION QUE HAY QUE TENER PRESENTE
--------------------------------------
Sin paginado ni orden por fecha, los departamentos de ML son casi siempre los mismos
48 por barrio. Casas y PH si se ven completos. O sea que ML aporta cobertura TOTAL en
casa/PH y una ventana fija en departamentos. No se compensa con mas pedidos porque no
hay forma permitida de pedir el resto.

DE DONDE SALE CADA DATO
-----------------------
Dos fuentes en la misma pagina, unidas por el id MLA (NO por posicion: el <script>
trae 50 items y el HTML 48 tarjetas, asi que cruzarlos por indice desalinea todo):

    tarjeta HTML   calle + altura, ambientes, banos, m2 cubiertos, precio, inmobiliaria
    ld+json        precio y moneda estructurados, m2, inmobiliaria, y sobre todo
                   `datePosted` -> la fecha de publicacion, en el 100% de los avisos

`numberOfRooms` del ld+json son DORMITORIOS, no ambientes: medido sobre 170 avisos da
`ambientes - 1` en el 84% y el 16% restante son monoambientes (1 amb / 1 room). Es el
unico lugar de donde sale el dormitorio, que es filtro duro del perfil.

LO QUE ESTE PORTAL NO DA
------------------------
`m2 totales` aparece en 6 de 240 tarjetas (2,5%). O sea que el EXTERIOR — el criterio
que mas pesa del score (25) y el duro `departamento_exterior_min_m2` — queda sin dato
en casi todos. No se inventa: van sin el campo y score.py los trata como "no evaluable"
(chip ambar "a preguntar"), que es lo correcto. Se resuelve con detalle.py, no aca.
"""

from __future__ import annotations

import gzip
import html as _html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import es_gba, load_config, normalizar_direccion  # noqa: E402

BASE = "https://inmuebles.mercadolibre.com.ar"

# El headline de la tarjeta -> el vocabulario del proyecto
TIPOS = {"departamento": "departamento", "casa": "casa", "ph": "ph"}

# (segmento de la URL, tipo del proyecto, faceta de ambientes)
# La faceta solo se usa en departamentos: casas y PH son tan pocos por barrio que
# entran enteros en una pagina y acotar solo tiraria inventario.
RUTAS = [
    ("departamentos", "departamento", "mas-de-3-ambientes"),
    ("casas", "casa", None),
    ("ph", "ph", None),
]


def _t(x: str | None) -> str | None:
    if x is None:
        return None
    t = _html.unescape(re.sub(r"<[^>]+>", " ", x))
    return re.sub(r"\s{2,}", " ", t).strip() or None


def _num(x) -> float | None:
    """'1.100.000' -> 1100000.0 · '79' -> 79.0. Formato argentino: el punto es miles."""
    if x is None:
        return None
    s = re.sub(r"[^\d,.]", "", str(x))
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".") if "," in s else s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _clase(frag: str, clase: str) -> str | None:
    m = re.search(r'class="[^"]*\b' + clase + r'\b[^"]*"[^>]*>(.*?)</', frag, re.S)
    return _t(m.group(1)) if m else None


def _mla(texto: str | None) -> str | None:
    m = re.search(r"MLA-?(\d+)", texto or "")
    return m.group(1) if m else None


# --------------------------------------------------------------------------- ld+json

def _indice_ld(html: str) -> dict:
    """{id MLA -> item}. Es la fuente de la fecha de publicacion y del dormitorio."""
    m = re.search(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return {}
    try:
        datos = json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}
    out = {}
    for it in datos.get("@graph") or []:
        if it.get("@type") != "RealEstateListing":
            continue
        pid = _mla((it.get("offers") or {}).get("url") or it.get("mainEntityOfPage"))
        if pid:
            out[pid] = it
    return out


# --------------------------------------------------------------------------- tarjeta

def _atributos(frag: str) -> dict:
    """'3 ambs.' · '2 banos' · '79 m2 cubiertos' · '120 m2 totales'."""
    out: dict = {}
    m = re.search(r"poly-attributes_list(.*?)</ul>", frag, re.S)
    if not m:
        return out
    for li in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.S):
        txt = (_t(li) or "").lower()
        cabeza = re.match(r"[\d.,]+", txt)
        n = _num(cabeza.group(0)) if cabeza else None
        if n is None:
            continue
        if "cubiert" in txt:
            out["m2_cubiertos"] = n
        elif "total" in txt:
            out["m2_totales"] = n
        elif "amb" in txt:
            # Un aviso cargado a mano puede decir "33 ambs.". Se descarta el valor
            # absurdo en vez de dejarlo entrar al filtro duro.
            if 1 <= n <= 15:
                out["ambientes_declarados"] = int(n)
        elif "bano" in txt or "baño" in txt:
            if 1 <= n <= 10:
                out["banos_declarados"] = int(n)
        elif "coch" in txt:
            out["cocheras"] = int(n)
    return out


def tarjeta_a_aviso(frag: str, ld: dict, barrio_busqueda: str | None = None,
                    tipo_ruta: str | None = None) -> dict | None:
    m_href = re.search(r'href="(https://[^"]*MLA-?\d+[^"]*)"', frag)
    if not m_href:
        return None
    url = _html.unescape(m_href.group(1)).split("#")[0]
    pid = _mla(url)
    if not pid:
        return None
    it = ld.get(pid, {})

    a: dict = {
        "id": "ml-" + pid,
        "portal": "mercadolibre",
        "id_portal": pid,
        "url": url,
        "titulo": _clase(frag, "poly-component__title") or _t(it.get("name")),
        "descripcion": None,   # el listado de ML no trae prosa; la trae la ficha
        "barrio": barrio_busqueda,
    }

    # --- direccion: "Blanco Encalada Al 5200, Villa Urquiza, Capital Federal"
    # El 100% de las tarjetas trae calle y altura, pero el 72% la da REDONDEADA A LA
    # CUADRA ("Al 5200"). No es un problema para deduplicar contra Zonaprop porque
    # Zonaprop redondea igual (Conde 4700, Vedia 3000, Paroissien 4400 son todos x00),
    # pero algun duplicado con altura exacta de un lado y cuadra del otro se va a
    # escapar. normalizar_direccion() ya saca el "al" delante del numero.
    loc = _clase(frag, "poly-component__location")
    if loc:
        partes = [p.strip() for p in loc.split(",")]
        a["direccion"] = partes[0] or None
        localidad = partes[1] if len(partes) > 1 else None
        if not a["barrio"]:
            a["barrio"] = localidad
        elif es_gba(a["barrio"]) and localidad and es_gba(localidad):
            # EN GBA SE PIDE EL PARTIDO Y VUELVEN SUS LOCALIDADES. Sin esto, los 84
            # avisos de `vicente-lopez` quedaban todos con barrio "Vicente Lopez" y se
            # perdia que 23 son de Olivos, 4 de Munro y 4 de Florida — que es justo el
            # nivel al que Mario mira el mapa. Se pisa el partido con la localidad SOLO
            # cuando la localidad tambien es de GBA Norte: hay tarjetas donde el
            # anunciante escribe cualquier cosa en ese campo ("Parrilla Y Playroom"),
            # y ahi es mejor quedarse con el partido, que al menos es cierto.
            a["barrio"] = localidad
    else:
        a["direccion"] = None
    a["direccion_norm"] = normalizar_direccion(a["direccion"])

    # --- tipo: el headline lo dice sin ambiguedad ("Departamento en alquiler")
    head = (_clase(frag, "poly-component__headline") or "").lower()
    a["tipo_declarado"] = _clase(frag, "poly-component__headline")
    a["tipo"] = next((v for k, v in TIPOS.items() if head.startswith(k)), tipo_ruta)

    # --- precio: del ld+json, que lo da estructurado. La tarjeta es el respaldo.
    of = it.get("offers") or {}
    monto, moneda = of.get("price"), (of.get("priceCurrency") or "").upper()
    if monto is None:
        monto = _num(_clase(frag, "andes-money-amount__fraction"))
        simbolo = (_clase(frag, "andes-money-amount__currency-symbol") or "").lower()
        moneda = "USD" if ("u$s" in simbolo or "us$" in simbolo) else "ARS"
    if monto is not None:
        a["moneda_publicacion"] = moneda if moneda in ("USD", "ARS") else "ARS"
        if a["moneda_publicacion"] == "USD":
            a["precio_alquiler_usd"] = float(monto)
        else:
            a["precio_alquiler_ars"] = float(monto)
        a["precio_texto"] = a["moneda_publicacion"] + " " + format(int(monto), ",d").replace(",", ".")

    # ML no publica expensas en el listado. No se inventa el campo en 0: declararlas
    # en cero haria pasar el duro `expensas_usd_max` a avisos que no dijeron nada.
    a["expensas_ars"] = None
    a["expensas_declaradas"] = False

    a.update(_atributos(frag))

    # --- superficie del ld+json si la tarjeta no la trajo
    fs = it.get("floorSize") or {}
    if a.get("m2_cubiertos") is None and fs.get("value"):
        a["m2_cubiertos"] = float(fs["value"])
    if a.get("m2_totales") and a.get("m2_cubiertos"):
        a["m2_descubiertos"] = max(0.0, a["m2_totales"] - a["m2_cubiertos"])
        a["m2_descubiertos_derivado"] = True

    # --- dormitorios: SOLO estan aca. Ver el encabezado del modulo: `numberOfRooms`
    # es dormitorios, no ambientes (medido, 84% da ambientes-1 y el resto monoambientes).
    nr = it.get("numberOfRooms")
    if isinstance(nr, (int, float)) and 0 < nr <= 15:
        a["dormitorios_declarados"] = int(nr)
    if a.get("banos_declarados") is not None:
        a["banos_completos"] = int(a["banos_declarados"])
    if a.get("cocheras") is not None:
        a["cochera"] = a["cocheras"] > 0

    # --- fecha de publicacion: ld+json la da ABSOLUTA y en el 100% de los avisos.
    # Es el mejor dato de fecha de los tres portales: en Zonaprop solo viene en la
    # pasada de novedades y hay que derivarla de "publicado hace N dias".
    dp = it.get("datePosted")
    if isinstance(dp, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", dp[:10]):
        a["publicado_el"] = dp[:10]
        a["fuente_fecha"] = "listado"

    # --- inmobiliaria
    a["publicador"] = (_clase(frag, "poly-component__seller")
                       or _t((it.get("seller") or {}).get("name")))
    a["publicador_url"] = None
    # ML no distingue al particular en la URL como hace Zonaprop con el slug `-pa-`, y
    # muchos avisos de inmobiliaria vienen sin vendedor en la tarjeta. Sin senal fiable
    # no se afirma: queda en None, igual que en Argenprop.
    a["dueno_directo"] = None

    # --- fotos. Van a `fotos_remotas` (se muestran en la pagina) porque el CDN de ML
    # SI responde cross-origin, a diferencia del de Argenprop. Verificado en el
    # navegador, no solo comprobando que la URL exista: es la leccion de la sesion 8.
    fotos = []
    for u in re.findall(r'(?:data-src|src)="(https://http2\.mlstatic\.com/[^"]+)"', frag):
        u = u.split("?")[0]
        if u not in fotos and not u.endswith(".gif"):
            fotos.append(u)
    if not fotos and it.get("image"):
        fotos.append(str(it["image"]).replace("http://", "https://").split("?")[0])
    a["fotos_remotas"] = fotos
    a["fotos_captions"] = []
    a["fuente_datos"] = "listado"
    return a


# --------------------------------------------------------------------------- pagina

def parsear_listado(html: str, barrio: str | None = None,
                    tipo_ruta: str | None = None) -> tuple[list[dict], dict]:
    ld = _indice_ld(html)
    trozos = re.split(r'(?=<li class="ui-search-layout__item)', html)
    avisos = []
    for t in trozos:
        if "poly-component__location" not in t:
            continue
        a = tarjeta_a_aviso(t, ld, barrio, tipo_ruta)
        if a:
            avisos.append(a)
    m = re.search(r"([\d][\d.]*)\s*resultados", html)
    total = int(_num(m.group(1)) or 0) if m else None
    return avisos, {"total": total, "en_pagina": len(avisos)}


# --------------------------------------------------------------------------- red

def slug(barrio: str) -> str:
    t = (barrio or "").lower().strip()
    for a, b in (("ñ", "n"), ("á", "a"), ("é", "e"),
                 ("í", "i"), ("ó", "o"), ("ú", "u")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def zonas_de(cfg: dict) -> list:
    """Los barrios de ESTE portal, que no son los de la busqueda general.

    Mario, 2026-08-23: "no pondria Palermo, ni Almagro, seria mas de Colegiales hasta
    Saavedra". Vive en `portales.mercadolibre_zonas` y no adentro del dict del portal
    porque el parser de YAML de este proyecto es por linea: una lista tiene que entrar
    entera en un renglon, y adentro de `{...}` no entra. (La lista partida en dos lineas
    fue lo que causo el 403 de la sesion 4.)
    """
    p = cfg.get("portales") or {}
    z = p.get("mercadolibre_zonas")
    if isinstance(z, str):      # misma defensa que lib_config: un string se itera por letra
        z = None
    return list(z) if z else list(cfg["zonas"]["incluidas"])


def url_busqueda(barrio: str, segmento: str, faceta: str | None = None) -> str:
    """No lleva pagina ni orden A PROPOSITO: robots.txt prohibe `_Desde_` y `_OrderId_`.

    LA GEOGRAFIA DE ML TIENE DOS RAMAS y la URL cambia de forma segun la rama:

        CABA  .../capital-federal/<barrio>/
        GBA   .../bsas-gba-norte/<partido>/            (opcionalmente /<localidad>/)

    La forma canonica salio del HTML del propio portal, que linkea
    `bsas-gba-norte/vicente-lopez/olivos`. El atajo `/casas/alquiler/olivos/` tambien
    funciona y devuelve lo mismo, pero NO se usa: con nombres ambiguos —"Florida",
    "San Isidro" es partido Y localidad— no hay forma de saber que resolvio el portal.
    Verificado el 2026-08-24: `bsas-gba-norte/vicente-lopez/` devuelve 84 casas de
    Olivos, Vicente Lopez, La Lucila, Munro y Florida.
    """
    partes = [BASE, segmento, "alquiler"]
    if faceta:
        partes.append(faceta)
    partes += (["bsas-gba-norte"] if es_gba(barrio) else ["capital-federal"])
    partes += [slug(barrio), ""]
    return "/".join(partes)


def bajar(url: str, cfg: dict) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": cfg["rate_limit"]["user_agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9",
        "Accept-Encoding": "gzip",
        "Connection": "close",
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        crudo = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            crudo = gzip.decompress(crudo)
        return crudo.decode("utf-8", errors="replace")


def buscar(barrios: list[str], cfg: dict | None = None,
           max_requests: int | None = None) -> list[dict]:
    cfg = cfg or load_config()
    rl = cfg.get("rate_limit", {})
    pausa = float(rl.get("pausa_segundos_min", 3))
    tope = int(max_requests if max_requests is not None else 30)
    todos: list[dict] = []
    pedidos = 0

    # CANARIO. Dos veces en este proyecto una URL mal armada costo una tanda entera de
    # pedidos (el 403 de Zonaprop y el 202 de Argenprop). Y la sesion 9 enseno la otra
    # mitad: un canario que solo pregunta "vinieron filas" no sirve, porque el barrido
    # de departamentos trajo 810 avisos de Montevideo y Punta del Este sin un error.
    # Este comprueba las dos cosas: que haya tarjetas Y que el barrio sea el pedido.
    if not barrios:
        return []
    prueba_barrio = barrios[0]
    try:
        html = bajar(url_busqueda(prueba_barrio, "departamentos", "mas-de-3-ambientes"), cfg)
    except urllib.error.HTTPError as e:
        print("  !  mercadolibre no responde (HTTP %s): no se barre" % e.code)
        return []
    pedidos += 1
    avisos, _ = parsear_listado(html, prueba_barrio, "departamento")
    if not avisos:
        print("  !  la URL de busqueda no trae tarjetas: "
              + url_busqueda(prueba_barrio, "departamentos", "mas-de-3-ambientes"))
        return []
    # EL CANARIO MIRA QUE VUELVA LA GEOGRAFIA PEDIDA, no solo que vengan filas (sesion 9:
    # 810 departamentos de Montevideo y Punta del Este con HTTP 200 y sin un error).
    # En GBA no se puede exigir el mismo nombre: se pide el PARTIDO `san-isidro` y vuelven
    # Martinez, Beccar y Acassuso, que son la respuesta correcta. Ahi se comprueba contra
    # las localidades del partido, que es lo que `es_gba` sabe.
    esperado = slug(prueba_barrio)
    devueltos = [slug(a.get("barrio") or "") for a in avisos if a.get("barrio")]
    if es_gba(prueba_barrio):
        aciertos = sum(1 for a in avisos if es_gba(a.get("barrio")))
        ok = not devueltos or aciertos >= len(devueltos) / 2
    else:
        ok = not devueltos or sum(d == esperado for d in devueltos) >= len(devueltos) / 2
    if not ok:
        print("  !  ML devolvio otro barrio: se pidio %r y volvieron %s. Se aborta."
              % (esperado, sorted(set(devueltos))[:4]))
        return []
    todos.extend(avisos)
    print("  %-16s %-14s %3d avisos" % (prueba_barrio, "departamentos", len(avisos)))

    techo_visto = techo_total = techo_busquedas = 0
    for i, barrio in enumerate(barrios):
        s = slug(barrio)
        # Misma defensa que fetch.py despues del 403: un slug vacio pide todo el pais.
        if not s or len(s) < 3:
            print("  !  barrio invalido en el config, se saltea: %r" % barrio)
            continue
        for segmento, tipo, faceta in RUTAS:
            if i == 0 and segmento == "departamentos":
                continue  # ya vino en el canario
            if pedidos >= tope:
                print("  !  tope de %d pedidos alcanzado; el resto queda para la "
                      "proxima corrida" % tope)
                return todos
            time.sleep(pausa)
            u = url_busqueda(barrio, segmento, faceta)
            try:
                html = bajar(u, cfg)
            except urllib.error.HTTPError as e:
                print("  !  %s %s: HTTP %s - se corta el portal" % (barrio, segmento, e.code))
                return todos
            pedidos += 1
            avisos, paging = parsear_listado(html, barrio, tipo)
            # EL TECHO DE 48 SE CUENTA, NO SE GRITA EN CADA LINEA.
            #
            # Antes esto imprimia "(de 288; el resto no es alcanzable sin paginar)" en
            # cada busqueda truncada, o sea en casi todas: el 2026-08-31 Mario lo leyo
            # como que el sistema estaba roto ("me salen carteles q no se puso paginar")
            # y penso que por eso habia dejado de barrer. NO es un error y no hay nada
            # que arreglar: el robots.txt de ML prohibe `_Desde_`, asi que de cada
            # busqueda se ve UNA pagina de 48 y el resto no es pedible. Pero repetido
            # diez veces por corrida deja de informar y pasa a alarmar: es la misma
            # leccion del chip ambar -"una senal que se enciende en todos deja de ser
            # una senal"-. Ahora va UNA linea al final con el total, que ademas es el
            # numero que de verdad importa: cuanto inventario de ML no se puede ver.
            if paging.get("total") and paging["total"] > len(avisos):
                techo_visto += len(avisos)
                techo_total += paging["total"]
                techo_busquedas += 1
            print("  %-16s %-14s %3d avisos" % (barrio, segmento, len(avisos)))
            todos.extend(avisos)

    if techo_busquedas:
        print("  i  %d de las busquedas de ML llegan al techo de una pagina: se ven "
              "%d de %d avisos. NO es un error ni se arregla pidiendo mas: su "
              "robots.txt prohibe paginar."
              % (techo_busquedas, techo_visto, techo_total))
    return todos


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "archivo":
        crudo = Path(args[1]).read_text(encoding="utf-8", errors="replace")
        avisos, paging = parsear_listado(crudo, args[2] if len(args) > 2 else None)
        print("%d avisos - paging=%s\n" % (len(avisos), paging))
        for a in avisos[:40]:
            print("  %-16s%-30s%-13s%s %-9s %sm2 %samb %sdorm  %s  %s" % (
                a["id"], str(a.get("direccion"))[:29], str(a.get("tipo")),
                a.get("moneda_publicacion"),
                a.get("precio_alquiler_usd") or a.get("precio_alquiler_ars"),
                a.get("m2_cubiertos"), a.get("ambientes_declarados"),
                a.get("dormitorios_declarados"), a.get("publicado_el"),
                str(a.get("publicador"))[:20]))
    else:
        cfg = load_config()
        print("MercadoLibre - %d barrios - %d rutas" % (len(zonas_de(cfg)), len(RUTAS)))
        r = buscar(zonas_de(cfg), cfg,
                   int(args[0]) if args and args[0].isdigit() else None)
        print("\n%d avisos bajados" % len(r))
