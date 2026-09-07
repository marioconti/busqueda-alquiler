"""Lectura de los listados de Zonaprop y deduplicacion.

DONDE ESTAN LOS DATOS *(verificado 2026-08-14)*
----------------------------------------------
No hay `__NEXT_DATA__`. Hay un `window.__PRELOADED_STATE__ = {...}` y adentro:

    listStore.listPostings[]   los avisos de la pagina (30 por pagina)
    listStore.paging           {currentPage, totalPages, total}

**El listado trae casi todo lo que trae la ficha de detalle**, y eso cambia la economia
del sistema: con UN request se consiguen 30 propiedades con descripcion completa, fotos,
expensas, antiguedad e inmobiliaria. Antes se creia que habia que abrir cada ficha.

Campos utiles de cada item:

    postingId, url, title, generatedTitle ("PH · 37m² · 2 Ambientes")
    realEstateType        {"name": "PH"|"Casa"|"Departamento"}
    postingLocation       address.name (la direccion) + location.name (el barrio)
    priceOperationTypes   precio y moneda
    expenses              {"amount": N}  <- las expensas, que la ficha no da tan facil
    antiquity             NO es la antiguedad: es "Publicado hace N dias" (ver
                          _dias_desde_antiquity). La antiguedad real es CFT5.
    mainFeatures          CFT100 total · CFT101 cubierta · CFT1 amb · CFT2 dorm · CFT3 banos
    visiblePictures       las fotos, con 5 tamanos cada una
    descriptionNormalized LA DESCRIPCION COMPLETA (habilita reglas.py sin abrir la ficha)
    publisher             la inmobiliaria: nombre y url

DEDUPLICACION: NUNCA por ID. Por direccion normalizada + m2 + rango de precio. Y al
encontrar un duplicado se FUSIONAN los campos: cada publicacion trae datos que la otra
omite (caso real: el mismo triplex publicado como Saavedra y como Belgrano, y solo la
version Belgrano decia "se alquila sin muebles").
"""

from __future__ import annotations

import html as _html
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import calle_y_altura, load_config, normalizar_direccion  # noqa: E402

RE_ESTADO = re.compile(r"window\.__PRELOADED_STATE__\s*=\s*")

MAPA_FEATURES = {
    "CFT100": "m2_totales",
    "CFT101": "m2_cubiertos",
    "CFT1": "ambientes_declarados",
    "CFT2": "dormitorios_declarados",
    "CFT3": "banos_declarados",
    "CFT4": "toilettes",             # el portal los separa: NO son banos completos
    "CFT5": "antiguedad_anios",
    "CFT7": "cocheras",
    "1000019": "disposicion",        # Frente / Contrafrente / Lateral -> tranquilidad
    "1000029": "orientacion",
    "1000027": "luminosidad",
}
TEXTUALES = {"orientacion", "luminosidad", "disposicion"}

# El portal escribe el tipo en PLURAL en las busquedas de departamentos ("Departamentos")
# y en singular en las de casa. La primera version solo tenia el singular: 856 avisos
# quedaron con tipo None, ninguno paso el filtro de tipo y la busqueda de departamentos
# devolvio cero sin un solo error. Un plural que no matchea no se queja: desaparece.
TIPOS = {"casa": "casa", "ph": "ph", "departamento": "departamento",
         "casa/ph": "ph", "duplex": "ph", "loft": "departamento",
         "casas": "casa", "phs": "ph", "departamentos": "departamento",
         "duplexs": "ph", "lofts": "departamento", "casas/ph": "ph"}


def _tipo_normalizado(nombre: str) -> str | None:
    """Tolera plural y espacios. Ante un tipo nuevo devuelve None, no adivina."""
    t = (nombre or "").strip().lower()
    return TIPOS.get(t) or TIPOS.get(t.rstrip("s"))


# --------------------------------------------------------------------------- json

def _bloque_balanceado(txt: str, i: int):
    """Lee un objeto JSON desde la llave que abre en `i`, respetando strings."""
    prof, j, en_str, comilla, escapado = 0, i, False, "", False
    while j < len(txt):
        c = txt[j]
        if en_str:
            if escapado:
                escapado = False
            elif c == "\\":
                escapado = True
            elif c == comilla:
                en_str = False
        elif c in "\"'":
            en_str, comilla = True, c
        elif c == "{":
            prof += 1
        elif c == "}":
            prof -= 1
            if prof == 0:
                return txt[i:j + 1]
        j += 1
    return None


def estado_precargado(html: str) -> dict | None:
    m = RE_ESTADO.search(html)
    if not m:
        return None
    crudo = _bloque_balanceado(html, m.end())
    if not crudo:
        return None
    try:
        return json.loads(crudo)
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- campos

def _numero(v):
    if v is None:
        return None
    m = re.search(r"[\d\.,]+", str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _texto(bruto: str | None) -> str | None:
    if not bruto:
        return None
    t = re.sub(r"<br\s*/?>", "\n", bruto, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip() or None


def _tipo_desde_slug(ruta: str) -> str | None:
    m = re.search(r"/(alcl)(ca|ph)(in|pa)-", ruta or "")
    return {"ca": "casa", "ph": "ph"}.get(m.group(2)) if m else None


def _particular_desde_slug(ruta: str) -> bool | None:
    m = re.search(r"/(alcl)(ca|ph)(in|pa)-", ruta or "")
    return None if not m else m.group(3) == "pa"


def _dias_desde_antiquity(txt) -> int | None:
    """"Publicado hace 14 dias" -> 14. HALLAZGO DEL 2026-08-21.

    El proyecto daba por sentado que `publicado_hace_dias` solo salia de la FICHA, y por
    eso lo tenia 1 de cada 3 candidatos: la vista "Ultimas 2 semanas" mostraba mas avisos
    sin fecha que con fecha. Estaba en el listado desde siempre, en el campo `antiquity`,
    en el 100% de los avisos (325 de 325 medidos). Cero requests extra.

    Vocabulario visto: "Publicado hoy" (0), "Publicado desde ayer" (1), "Publicado hace N
    dias". Cualquier otra forma devuelve None: inventar una fecha es peor que no tenerla.
    """
    if not isinstance(txt, str):
        return None
    t = txt.lower()
    if "publicado" not in t:
        return None
    if "hoy" in t:
        return 0
    if "ayer" in t:
        return 1
    m = re.search(r"hace\s+(\d+)", t)
    return int(m.group(1)) if m else None


def item_a_aviso(it: dict, barrio_busqueda: str | None = None,
                 fecha_barrido: date | None = None) -> dict | None:
    pid = it.get("postingId")
    if not pid:
        return None

    url = it.get("url") or ""
    if url and not url.startswith("http"):
        url = "https://www.zonaprop.com.ar" + url

    a: dict = {
        "id": f"zp-{pid}",
        "portal": "zonaprop",
        "id_portal": str(pid),
        "url": url,
        "titulo": _texto(it.get("title")),
        "titulo_generado": it.get("generatedTitle"),
        "descripcion": _texto(it.get("descriptionNormalized")),
    }

    tipo = ((it.get("realEstateType") or {}).get("name") or "").strip().lower()
    a["tipo"] = _tipo_normalizado(tipo) or _tipo_desde_slug(url)
    a["tipo_declarado"] = (it.get("realEstateType") or {}).get("name")

    loc = it.get("postingLocation") or {}
    a["direccion"] = (loc.get("address") or {}).get("name")
    a["direccion_visibilidad"] = (loc.get("address") or {}).get("visibility")
    a["barrio"] = (loc.get("location") or {}).get("name") or barrio_busqueda

    # --- precio
    for op in it.get("priceOperationTypes") or []:
        if ((op.get("operationType") or {}).get("operationTypeId")) != "2":
            continue  # 2 = alquiler
        for p in op.get("prices") or []:
            monto, moneda = p.get("amount"), (p.get("currency") or "").strip()
            if not monto:
                continue
            if moneda in ("USD", "U$S", "US$"):
                a["precio_alquiler_usd"] = float(monto)
                a["moneda_publicacion"] = "USD"
            else:
                a["precio_alquiler_ars"] = float(monto)
                a["moneda_publicacion"] = "ARS"
            a["precio_texto"] = f'{moneda} {p.get("formattedAmount") or monto}'
            break

    exp = it.get("expenses") or {}
    a["expensas_ars"] = float(exp["amount"]) if exp.get("amount") else None
    a["expensas_declaradas"] = bool(exp.get("amount"))

    # --- superficies y ambientes
    for cft, info in (it.get("mainFeatures") or {}).items():
        campo = MAPA_FEATURES.get(cft)
        if not campo:
            continue
        valor = info.get("value")
        a[campo] = valor if campo in TEXTUALES else _numero(valor)

    # `antiquity` NO ES LA ANTIGUEDAD DEL EDIFICIO. Es el texto de cuando se publico el
    # aviso: "Publicado hoy", "Publicado desde ayer", "Publicado hace 35 dias". Hasta el
    # 2026-08-21 se usaba como fallback de antiguedad_anios y _numero() le sacaba el
    # numero: 10 de cada 148 avisos quedaban con un edificio de "35 anios" que en realidad
    # era un aviso de 35 dias. Un campo mal leido es peor que un campo vacio, porque nadie
    # lo vuelve a mirar.
    dias_pub = _dias_desde_antiquity(it.get("antiquity"))
    if dias_pub is not None:
        a["publicado_hace_dias"] = dias_pub
        # Y la fecha ABSOLUTA, que es la que no envejece mal: "hace 2 dias" guardado en
        # la base sigue diciendo 2 dias dentro de un mes si el aviso no vuelve a salir en
        # un barrido. build.py recalcula los dias desde aca en cada corrida.
        # La fecha del BARRIDO, no la de hoy: al reprocesar un HTML guardado hace una
        # semana, "publicado hace 2 dias" son dos dias antes de ESE dia, no de este.
        a["publicado_el"] = ((fecha_barrido or date.today()) - timedelta(days=dias_pub)).isoformat()
        a["fuente_fecha"] = "listado"

    # `antiquity` viene poblado SOLO en los listados pedidos con
    # `-orden-publicado-descendente`; en los de precio-ascendente es None. Por eso la
    # fecha la trae la pasada de novedades y no la de cobertura.
    #
    # `modified_date` esta en el 100% de los avisos de las dos pasadas, pero NO es la
    # fecha de publicacion y no se usa como tal: medido sobre 205 avisos, coincide en el
    # 59% y cae al 71% aceptando un dia de error. Un aviso de hace ocho meses reeditado
    # ayer se mostraria como NUEVO, que es exactamente lo que la vista de dos semanas no
    # puede hacer. Se guarda como lo que es: la ultima vez que el anunciante lo toco.
    if isinstance(it.get("modified_date"), str):
        a["modificado_el"] = it["modified_date"][:10]

    # El portal cuenta banos y toilettes por separado: CFT3 son los completos.
    if a.get("banos_declarados") is not None:
        a["banos_completos"] = int(a["banos_declarados"])
    if a.get("toilettes") is not None:
        a["toilettes"] = int(a["toilettes"])
    if a.get("cocheras") is not None:
        a["cochera"] = a["cocheras"] > 0

    disp = (a.get("disposicion") or "").strip().lower()
    if disp:
        a["al_frente"] = disp.startswith("frente")
        if disp.startswith("contrafrente"):
            a["al_frente"] = False

    # --- inmobiliaria (alimenta conocimiento/inmobiliarias.md)
    pub = it.get("publisher") or {}
    a["publicador"] = pub.get("name")
    a["publicador_url"] = ("https://www.zonaprop.com.ar" + pub["url"]) if pub.get("url") else None
    a["dueno_directo"] = _particular_desde_slug(url)
    if a["dueno_directo"] is None and pub.get("publisherId") is None:
        a["dueno_directo"] = True

    # --- fotos: se guardan las URL remotas. Bajar 6 fotos de cientos de avisos seria
    # absurdo; solo se bajan a local las de la lista corta (scripts/detalle.py).
    fotos, captions = [], []
    for p in ((it.get("visiblePictures") or {}).get("pictures") or []):
        u = p.get("url730x532") or p.get("url720x532") or p.get("url360x266")
        if u:
            fotos.append(u.split("?")[0])
            captions.append(p.get("title"))
    a["fotos_remotas"] = fotos
    a["fotos_captions"] = captions
    a["fuente_datos"] = "listado"
    return a


# --------------------------------------------------------------------------- pagina

def parsear_listado(html: str, barrio: str | None = None,
                    fecha_barrido: date | None = None) -> tuple[list[dict], dict]:
    """Devuelve (avisos, paging). paging = {currentPage, totalPages, total}."""
    estado = estado_precargado(html)
    if not estado:
        return [], {}
    lista = (estado.get("listStore") or {})
    avisos = []
    for it in lista.get("listPostings") or []:
        a = item_a_aviso(it, barrio, fecha_barrido)
        if a:
            avisos.append(a)
    return avisos, (lista.get("paging") or {})


# --------------------------------------------------------------------------- dedup

def clave_dedup(a: dict) -> tuple | None:
    """direccion normalizada + m2 cubiertos. NUNCA el id, y NUNCA el precio.

    EL PRECIO SALIO DE LA CLAVE, y esa fue la correccion importante. Casos reales de la
    primera corrida grande:

      Conde 4700   publicado por la MISMA inmobiliaria dos veces, una en pesos
                   ($ 2.400.000) y otra en dolares (USD 1.590). Con el precio en la clave
                   nunca matcheaban: quedaban tres Conde 4700 en la lista.
      Malasia 800  la misma casa de 300 m2 listada por tres inmobiliarias distintas a
                   USD 4.500, 4.900 y 5.200.

    Una propiedad es la misma aunque tres agencias le pongan tres precios. Lo que la
    identifica es la direccion y los metros cubiertos.

    Devuelve None cuando no hay altura o no hay m2: sin esos dos no se puede afirmar que
    dos avisos son el mismo inmueble, y **fusionar de mas es peor que mostrar de mas**.
    """
    calle, altura = calle_y_altura(a.get("direccion_norm") or normalizar_direccion(a.get("direccion")))
    m2 = a.get("m2_cubiertos")
    if not calle or altura is None or m2 is None:
        return None
    return (calle, altura, round(float(m2) / 10))


def fusionar(destino: dict, origen: dict) -> dict:
    for k, v in origen.items():
        if v in (None, [], "", {}):
            continue
        actual = destino.get(k)
        if actual in (None, [], "", {}):
            destino[k] = v
        elif isinstance(actual, list) and isinstance(v, list) and len(v) > len(actual):
            destino[k] = v
    dups = destino.setdefault("duplicados", [])
    if origen.get("url") and origen["url"] != destino.get("url"):
        if origen["url"] not in [d.get("url") for d in dups]:
            dups.append({"url": origen["url"], "portal": origen.get("portal"),
                         "barrio": origen.get("barrio"), "publicador": origen.get("publicador")})
    return destino


def _prioridad(a: dict) -> tuple:
    """Cuando dos avisos son el mismo inmueble, cual sobrevive.

    Gana el marcado a mano (para no perder un favorito ni su numero), despues el que ya
    estaba en la base, despues el que tiene mas datos.
    """
    return (0 if a.get("pinned") else 1,
            0 if a.get("num") else 1,
            a.get("first_seen") or "9999",
            -sum(1 for v in a.values() if v not in (None, [], "", {})))


def deduplicar(avisos: list[dict]) -> list[dict]:
    """Fusiona por id y por (direccion + m2). El sobreviviente absorbe al resto.

    Se corre sobre TODO el inventario, no solo sobre lo recien bajado: si no, un aviso
    nuevo que es el mismo inmueble que uno viejo nunca se compara con el. Asi aparecieron
    tres Conde 4700 (uno en la base + dos del barrido).
    """
    por_id: dict[str, dict] = {}
    for a in avisos:
        a["direccion_norm"] = normalizar_direccion(a.get("direccion"))
        if a["id"] in por_id:
            fusionar(por_id[a["id"]], a)
        else:
            por_id[a["id"]] = a

    grupos: dict[tuple, list[dict]] = {}
    sueltos: list[dict] = []
    for a in por_id.values():
        k = clave_dedup(a)
        if k is None:
            sueltos.append(a)
        else:
            grupos.setdefault(k, []).append(a)

    salida = list(sueltos)
    for miembros in grupos.values():
        miembros.sort(key=_prioridad)
        principal = miembros[0]
        for otro in miembros[1:]:
            fusionar(principal, otro)
            principal.setdefault("ids_absorbidos", [])
            if otro["id"] not in principal["ids_absorbidos"]:
                principal["ids_absorbidos"].append(otro["id"])
        salida.append(principal)
    return salida


def es_basura(a: dict, cfg: dict) -> bool:
    texto = " ".join(str(a.get(c) or "") for c in ("titulo", "descripcion")).lower()
    if any(t in texto for t in cfg["basura"]["textos_descarte"]):
        return True
    tot = a.get("m2_totales")
    return tot is not None and float(tot) > float(cfg["basura"]["m2_totales_max"])


def parsear_todo(bajados: dict[str, str]) -> list[dict]:
    cfg = load_config()
    crudos: list[dict] = []
    for etiqueta, ruta in bajados.items():
        partes = etiqueta.split("/")
        barrio = partes[1].replace("-", " ").title() if len(partes) > 1 else None
        # El HTML vive en data/raw/<fecha>/: esa es la fecha en la que el portal dijo
        # "publicado hace N dias", y es contra la que hay que fechar.
        try:
            y, m, d = (int(x) for x in Path(ruta).parent.name.split("-"))
            fecha_barrido = date(y, m, d)
        except ValueError:
            fecha_barrido = None
        html = Path(ruta).read_text(encoding="utf-8", errors="replace")
        avisos, _ = parsear_listado(html, barrio, fecha_barrido)
        crudos.extend(avisos)
    limpios = [a for a in crudos if not es_basura(a, cfg)]
    return deduplicar(limpios)


if __name__ == "__main__":
    from fetch import DIR_CRUDO

    dias = sorted(p for p in DIR_CRUDO.glob("*") if p.is_dir())
    if not dias:
        raise SystemExit("no hay descargas en data/raw/ — correr fetch.py primero")
    archivos = {p.stem.replace("__", "/"): str(p) for p in dias[-1].glob("*.html")}
    avisos = parsear_todo(archivos)
    print(f"{len(avisos)} avisos unicos desde {dias[-1].name} ({len(archivos)} paginas)")
    por_barrio: dict[str, int] = {}
    for a in avisos:
        por_barrio[a.get("barrio") or "?"] = por_barrio.get(a.get("barrio") or "?", 0) + 1
    for b, n in sorted(por_barrio.items(), key=lambda x: -x[1]):
        print(f"  {b:24s} {n}")
