"""Argenprop: segundo portal. Devuelve avisos con el MISMO esquema que parse.py.

POR QUE ARGENPROP Y NO OTRO
---------------------------
Se sondearon cuatro portales (2026-08-14, un pedido a cada uno, respetando robots.txt):

    Argenprop     robots permite la busqueda · 20 avisos por pagina · HTML plano
    MercadoLibre  robots permite · pero "casas/alquiler/saavedra" devuelve 11 resultados
    Remax         robots permite · SPA contra API propia · su stock ya va a Zonaprop
    Properati     robots permite · MISMO grupo que Zonaprop -> inventario duplicado

Argenprop es el unico que suma inventario propio con esfuerzo razonable. Ademas es donde
publican las inmobiliarias chicas de barrio, que es justo lo que este mercado tiene:
el anunciante mas grande de Zonaprop tiene 8 avisos de 320.

LO QUE HACE FACIL ESTE PORTAL
-----------------------------
Los datos duros NO estan en la prosa: viajan como ATRIBUTOS del <a class="card">.

    idaviso="19994395"        idanunciante="141471"    idbarrio="25"
    dormitorios="1"           ambientes=""             idtipopropiedad="2"
    idmoneda="1"              montooperacion="1100000" montonormalizado="660"

`montonormalizado` es el precio llevado a una unidad comun por el portal; NO se usa como
precio en dolares porque no esta documentado a que cotizacion lo hace. El precio sale de
`montooperacion` + `idmoneda`, y la conversion la hace cotizacion.py como con Zonaprop.

Sin dependencias externas: el HTML se lee con expresiones regulares acotadas a cada
tarjeta, no con un parser de arbol.
"""

from __future__ import annotations

import html as _html
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import load_config, normalizar_direccion, zonas_a_barrer  # noqa: E402

BASE = "https://www.argenprop.com"

# idtipopropiedad del portal -> el vocabulario del proyecto
TIPOS = {"1": "departamento", "2": "ph", "3": "casa", "4": "casa", "12": "departamento"}

# En el markup: <span class="card__currency">$</span> o U$S
MONEDAS = {"$": "ARS", "u$s": "USD", "us$": "USD", "usd": "USD"}


def _t(x: str | None) -> str | None:
    """Texto de HTML: desescapa entidades y aplasta espacios."""
    if x is None:
        return None
    t = re.sub(r"<[^>]+>", " ", x)
    t = _html.unescape(t)
    t = re.sub(r"[\r\n\t]+", "\n", t)
    t = re.sub(r"[  ]{2,}", " ", t)
    return t.strip() or None


def _num(x) -> float | None:
    if x is None:
        return None
    s = re.sub(r"[^\d,.-]", "", str(x))
    if not s:
        return None
    # formato argentino: 1.100.000,50
    s = s.replace(".", "").replace(",", ".") if "," in s else s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _attr(frag: str, nombre: str) -> str | None:
    m = re.search(rf'\b{nombre}="([^"]*)"', frag)
    return m.group(1).strip() or None if m else None


def _clase(frag: str, clase: str) -> str | None:
    """Contenido del primer elemento con esa clase exacta."""
    m = re.search(rf'class="{clase}[ "][^>]*>(.*?)</(?:p|h2|div|span|li)>', frag, re.S)
    return _t(m.group(1)) if m else None


# --------------------------------------------------------------------------- tarjeta

def _features(frag: str) -> dict:
    """La lista <ul class="card__main-features"> trae '57 m2 cubie.', '1 dorm.', '30 anios'."""
    out: dict = {}
    m = re.search(r'class="card__main-features"[^>]*>(.*?)</ul>', frag, re.S)
    if not m:
        return out
    for li in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.S):
        txt = (_t(li) or "").lower()
        n = _num(re.sub(r"m.?2|años?|anios?", " ", txt))
        if n is None:
            continue
        if "cubie" in txt:
            out["m2_cubiertos"] = n
        elif "tot" in txt or "m²" in txt or "m2" in txt:
            out["m2_totales"] = n
        elif "dorm" in txt:
            out["dormitorios_declarados"] = int(n)
        elif "amb" in txt:
            out["ambientes_declarados"] = int(n)
        elif "baño" in txt or "bano" in txt:
            out["banos_declarados"] = int(n)
        elif "año" in txt or "anio" in txt or "antigu" in txt:
            out["antiguedad_anios"] = n
        elif "coch" in txt:
            out["cocheras"] = int(n)
    return out


def tarjeta_a_aviso(frag: str, barrio_busqueda: str | None = None) -> dict | None:
    pid = _attr(frag, "idaviso") or _attr(frag, "data-item-card")
    if not pid:
        return None

    m_href = re.search(r'href="(/[^"]+--\d{4,})"', frag)
    url = BASE + m_href.group(1) if m_href else None

    a: dict = {
        "id": f"ap-{pid}",
        "portal": "argenprop",
        "id_portal": str(pid),
        "url": url,
        "titulo": _clase(frag, "card__title"),
        "descripcion": _clase(frag, "card__info"),
        "direccion": _clase(frag, "card__address"),
        "barrio": barrio_busqueda,
    }
    a["direccion_norm"] = normalizar_direccion(a["direccion"])

    # "PH en Alquiler en Saavedra, Capital Federal" -> barrio, si no vino por parametro
    prim = _clase(frag, "card__title--primary") or ""
    m_b = re.search(r"\ben\s+([^,]+),\s*Capital Federal", prim, re.I)
    if m_b and not a["barrio"]:
        a["barrio"] = m_b.group(1).strip()
    a["tipo_declarado"] = prim.split(" en ")[0].strip() if " en " in prim else None
    a["tipo"] = TIPOS.get(_attr(frag, "idtipopropiedad") or "")
    if not a["tipo"] and url:
        slug = url.rsplit("/", 1)[-1]
        a["tipo"] = ("ph" if slug.startswith("ph-") else
                     "casa" if slug.startswith("casa-") else
                     "departamento" if slug.startswith(("departamento-", "depto-")) else None)

    # --- precio: monto crudo + moneda declarada. La conversion la hace cotizacion.py.
    monto = _num(_attr(frag, "montooperacion"))
    simbolo = (_clase(frag, "card__currency") or "").lower()
    moneda = MONEDAS.get(simbolo)
    if moneda is None and monto is not None:
        # sin simbolo legible: un alquiler de 6 cifras en CABA es pesos, no dolares
        moneda = "ARS" if monto >= 100_000 else "USD"
    a["moneda_publicacion"] = moneda
    a["precio_texto"] = _clase(frag, "card__price")
    if monto is not None:
        if moneda == "USD":
            a["precio_alquiler_usd"] = monto
        else:
            a["precio_alquiler_ars"] = monto

    # --- expensas: Argenprop las mete en el texto, no en un campo aparte
    exp = None
    if a["descripcion"]:
        m_e = re.search(r"expensas?[^\n\d]{0,20}\$\s*([\d\.]+)", a["descripcion"], re.I)
        if m_e:
            exp = _num(m_e.group(1))
    a["expensas_ars"] = exp
    a["expensas_declaradas"] = exp is not None

    a.update(_features(frag))
    if a.get("dormitorios_declarados") is None:
        d = _attr(frag, "dormitorios")
        if d and d.isdigit():
            a["dormitorios_declarados"] = int(d)
    if a.get("ambientes_declarados") is None:
        amb = _attr(frag, "ambientes")
        if amb and amb.isdigit():
            a["ambientes_declarados"] = int(amb)
    if a.get("banos_declarados") is not None:
        a["banos_completos"] = int(a["banos_declarados"])
    if a.get("cocheras") is not None:
        a["cochera"] = a["cocheras"] > 0
    if a.get("m2_totales") and a.get("m2_cubiertos"):
        a["m2_descubiertos"] = max(0.0, a["m2_totales"] - a["m2_cubiertos"])
        a["m2_descubiertos_derivado"] = True

    # --- inmobiliaria: viene en el alt del logo. Alimenta conocimiento/inmobiliarias.md
    m_ag = re.search(r'class="card__agent"[^>]*>(.*?)</div>', frag, re.S)
    if m_ag:
        m_alt = re.search(r'alt="([^"]+)"', m_ag.group(1))
        a["publicador"] = _t(m_alt.group(1)) if m_alt else None
    a["publicador_id"] = _attr(frag, "idanunciante")
    # Argenprop no marca al particular en la URL como Zonaprop: sin logo NO alcanza para
    # afirmar dueno directo (hay inmobiliarias que no cargan logo). Queda en None.
    a["dueno_directo"] = None

    # NO reescribir el tamano. La primera version cambiaba "_u_small" por "_u_extra_large"
    # suponiendo que el CDN servia el mismo id en varios tamanos: el navegador devolvio
    # ERR_BLOCKED_BY_ORB en las 12 y las tarjetas de Argenprop quedaron sin foto. Se usan
    # las URL tal como las publica el portal.
    fotos = re.findall(r'(?:data-)?src="(https://www\.argenprop\.com/static-content/[^"]+)"', frag)
    vistas, limpias = set(), []
    for f in fotos:
        if f not in vistas:
            vistas.add(f)
            limpias.append(f)
    # NO van a `fotos_remotas`. El CDN de Argenprop rechaza el pedido cross-origin
    # (ERR_BLOCKED_BY_ORB en el navegador, en cualquier tamano): son URL validas para
    # BAJAR con detalle.py, pero inservibles para mostrar. Si vivieran en `fotos_remotas`
    # la pagina intentaria cargarlas y quedaria un hueco gris, y peor: al fusionar un
    # duplicado se llevaban puestas las fotos de Zonaprop, que si funcionan.
    a["fotos_remotas"] = []
    a["fotos_portal"] = limpias
    a["fotos_captions"] = []
    a["fuente_datos"] = "listado"
    return a


# --------------------------------------------------------------------------- pagina

def parsear_listado(html: str, barrio: str | None = None) -> tuple[list[dict], dict]:
    """(avisos, paging). Corta el HTML por tarjeta antes de mirar nada."""
    trozos = re.split(r'(?=<a\s[^>]*class="card\s)', html)
    avisos = []
    for t in trozos:
        if "idaviso=" not in t[:1200]:
            continue
        a = tarjeta_a_aviso(t, barrio)
        if a:
            avisos.append(a)

    total = None
    m = re.search(r"([\d\.]+)\s*(?:propiedades|resultados|avisos)", html, re.I)
    if m:
        total = int(_num(m.group(1)) or 0)
    paginas = [int(x) for x in re.findall(r'pagina-(\d+)', html)]
    return avisos, {"total": total, "totalPages": max(paginas) if paginas else None}


# --------------------------------------------------------------------------- red

def slug(barrio: str) -> str:
    t = (barrio or "").lower().strip()
    t = t.replace("ñ", "n").replace("á", "a").replace("é", "e").replace("í", "i")
    t = t.replace("ó", "o").replace("ú", "u")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def url_busqueda(barrio: str, pagina: int = 1) -> str:
    """casa-y-ph = casa + PH + duplex. Departamentos quedan afuera a proposito: el perfil
    los acepta solo con terraza propia amplia y en 400 revisados no salio ninguno.

    OJO CON LA FORMA DE LA URL. El HTML trae un atributo `data-change-view` con la forma
    "/casas-o-ph/alquiler/saavedra", que parece la canonica y devuelve CERO tarjetas. La que
    sirve es la que usa el sitio para navegar: "/casa-y-ph-alquiler-barrio-saavedra".
    Verificado contra HTML guardado: 20 tarjetas.
    """
    b = slug(barrio)
    u = f"{BASE}/casa-y-ph-alquiler-barrio-{b}"
    return u if pagina <= 1 else f"{u}-pagina-{pagina}"


def bajar(url: str, cfg: dict) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": cfg["rate_limit"]["user_agent"],
        "Accept-Language": "es-AR,es;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def buscar(barrios: list[str], max_paginas: int = 3, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    pausa = float(cfg.get("rate_limit", {}).get("pausa_segundos_min", 3))
    todos: list[dict] = []

    # CANARIO. El 2026-08-14 arme mal la URL de busqueda (la saque de un atributo del HTML
    # en vez de la que usa el sitio para navegar) y el barrido pidio los 9 barrios con una
    # URL que devuelve 200 y cero tarjetas. Nueve pedidos inutiles, y sumados a los del
    # sondeo alcanzaron para que Argenprop empezara a contestar 202 con cuerpo vacio.
    # Una URL equivocada cuesta pedidos igual que una correcta: se prueba UNA antes de
    # barrer, y si no trae tarjetas se aborta todo.
    if barrios:
        try:
            prueba = bajar(url_busqueda(barrios[0], 1), cfg)
        except urllib.error.HTTPError as e:
            print(f"  !  argenprop no responde (HTTP {e.code}): no se barre")
            return []
        if not prueba.strip():
            print("  !  argenprop devolvio cuerpo vacio (202 = mitigacion de bots). "
                  "NO se reintenta ni se cambia el user-agent: se corta y se avisa.")
            return []
        # La mitigacion tiene DOS caras y solo se conocia una. Ademas del 202 con cuerpo
        # vacio de la sesion 7, el 2026-08-24 devolvio 200 con una pagina de desafio de
        # 2.610 bytes: <title> vacio, estilos inline, ni una tarjeta. El mensaje de abajo
        # decia "la URL no trae tarjetas" y mandaba a revisar una URL que estaba bien:
        # costo un pedido darse cuenta. Un listado real de este portal no baja de 500 KB.
        if len(prueba) < 20_000:
            print(f"  !  argenprop devolvio una pagina de {len(prueba)} bytes sin listado: "
                  "es su mitigacion de bots, NO la URL. Se corta y se reintenta manana.")
            return []
        if not parsear_listado(prueba, barrios[0])[0]:
            print("  !  la URL de busqueda no trae tarjetas: " + url_busqueda(barrios[0], 1))
            print("     Se aborta el barrido en vez de pedir todos los barrios al pedo.")
            return []
        time.sleep(pausa)

    for barrio in barrios:
        s = slug(barrio)
        # Misma defensa que fetch.py despues del 403: un slug vacio pide "todo el pais".
        if not s or len(s) < 3:
            print(f"  !  barrio invalido en el config, se saltea: {barrio!r}")
            continue
        for pagina in range(1, max_paginas + 1):
            u = url_busqueda(barrio, pagina)
            try:
                html = bajar(u, cfg)
            except urllib.error.HTTPError as e:
                print(f"  !  {barrio} p{pagina}: HTTP {e.code} — se corta este barrio")
                break
            avisos, paging = parsear_listado(html, barrio)
            print(f"  {barrio:16} p{pagina}  {len(avisos):3} avisos"
                  f"{'  (total ' + str(paging['total']) + ')' if paging.get('total') else ''}")
            if not avisos:
                break
            todos.extend(avisos)
            time.sleep(pausa)
    return todos


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "archivo":          # desarrollo: parsear un HTML guardado
        crudo = Path(args[1]).read_text(encoding="utf-8", errors="replace")
        avisos, paging = parsear_listado(crudo, args[2] if len(args) > 2 else None)
        print(f"{len(avisos)} avisos · paging={paging}")
        for a in avisos:
            print(f'  {a["id"]:<14}{str(a.get("direccion"))[:26]:<28}'
                  f'{a.get("moneda_publicacion")} {a.get("precio_alquiler_ars") or a.get("precio_alquiler_usd")}'
                  f'  {a.get("m2_cubiertos")} m2  {a.get("dormitorios_declarados")} dorm'
                  f'  {str(a.get("publicador"))[:24]}')
    else:
        cfg = load_config()
        zonas = zonas_a_barrer(cfg)
        print(f"Argenprop · {len(zonas)} barrios")
        r = buscar(zonas, int(args[0]) if args and args[0].isdigit() else 2, cfg)
        print(f"\n{len(r)} avisos bajados")
