"""Ficha de detalle de Zonaprop: extrae los campos duros y baja las fotos a local.

Por que existe aparte de parse.py: el LISTADO trae poco y miente (el campo `dorm.` es
el caso conocido). La FICHA trae los metros discriminados entre totales y cubiertos, la
antiguedad, la orientacion, la fecha real de publicacion y la descripcion completa. Es
mas cara (un request por aviso) pero es la que decide.

Corre tambien como REVALIDACION: si la ficha devuelve 404 o la pagina de "aviso no
disponible", el aviso se marca desaparecido. Para un favorito, eso es lo que hay que
avisar el mismo dia.

Sin dependencias externas.

DONDE ESTAN LOS DATOS (verificado 2026-08-14 contra una ficha real)
-------------------------------------------------------------------
No hay `__NEXT_DATA__` ni `__PRELOADED_STATE__`. Hay un bloque de script con
asignaciones de la forma  'clave': <valor JSON o string>  . Las que sirven:

    'pictures'                  lista de fotos, 5 variantes de tamano c/u + caption
    'mainFeatures'              CFT100 tot. m2 · CFT101 cub. m2 · CFT1 amb · CFT2 dorm
                                CFT3 banos · CFT5 antiguedad · 1000029 orientacion
                                1000027 luminosidad
    'description'               descripcion completa, con HTML adentro
    'price'                     'USD 1.400'
    'publicationDateFormatted'  ISO de la PRIMERA publicacion
    'address'                   {"name": "Giribone 1980", "visibility": "EXACT"}
    'realEstateType'            {"name": "Casa", ...}
    'publisherTypeId'           1 = particular (dueno directo)

**CFT100 es TOTAL y CFT101 es CUBIERTA.** Confundirlas es el error que tenia la semilla
cargada a mano: Giribone 1980 figuraba con 120 m2 cubiertos y en realidad son 120
TOTALES y 80 cubiertos.
"""

from __future__ import annotations

import gzip
import html as _html
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import DIR_DATA, DIR_WEB, escribir_json, leer_json, load_config  # noqa: E402

DIR_FOTOS = DIR_WEB / "fotos"

SIN_AVISO = ("el aviso que buscas no", "aviso no disponible", "ya no est&aacute; disponible",
             "no se encuentra disponible", "aviso dado de baja")

MAPA_FEATURES = {
    "CFT100": "m2_totales",
    "CFT101": "m2_cubiertos",
    "CFT1": "ambientes_declarados",
    "CFT2": "dormitorios_declarados",
    "CFT3": "banos_declarados",
    "CFT4": "toilettes",             # el portal los separa: NO son banos completos
    "CFT5": "antiguedad_anios",
    "CFT7": "cocheras",
    "1000019": "disposicion",        # Frente / Contrafrente -> alimenta tranquilidad
    "1000029": "orientacion",
    "1000027": "luminosidad",
}
TEXTUALES = {"orientacion", "luminosidad", "disposicion"}


# --------------------------------------------------------------------------- red

def bajar_html(url: str, cfg: dict) -> str | None:
    """None = el aviso ya no existe (404/410). Excepcion = problema de red."""
    rl = cfg["rate_limit"]
    req = urllib.request.Request(url, headers={
        "User-Agent": rl["user_agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9",
        "Accept-Encoding": "gzip",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            crudo = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                crudo = gzip.decompress(crudo)
            return crudo.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return None
        raise


def dormir(cfg: dict, factor: float = 1.0) -> None:
    rl = cfg["rate_limit"]
    time.sleep(random.uniform(float(rl["pausa_segundos_min"]),
                              float(rl["pausa_segundos_max"])) * factor)


# --------------------------------------------------------------------------- parseo

def _valor_js(html: str, clave: str):
    """Lee  'clave': <valor>  donde el valor es un JSON balanceado o un string citado."""
    m = re.search(r"'" + re.escape(clave) + r"'\s*:\s*", html)
    if not m:
        return None
    i = m.end()
    if i >= len(html):
        return None
    ch = html[i]

    if ch in "{[":
        cierre = {"{": "}", "[": "]"}[ch]
        prof, j, en_str, comilla, escapado = 0, i, False, "", False
        while j < len(html):
            c = html[j]
            if en_str:
                if escapado:
                    escapado = False
                elif c == "\\":
                    escapado = True
                elif c == comilla:
                    en_str = False
            elif c in "\"'":
                en_str, comilla = True, c
            elif c == ch:
                prof += 1
            elif c == cierre:
                prof -= 1
                if prof == 0:
                    try:
                        return json.loads(html[i:j + 1])
                    except json.JSONDecodeError:
                        return None
            j += 1
        return None

    if ch in "\"'":
        j, escapado = i + 1, False
        while j < len(html):
            c = html[j]
            if escapado:
                escapado = False
            elif c == "\\":
                escapado = True
            elif c == ch:
                crudo = html[i:j + 1]
                if ch == '"':
                    try:
                        return json.loads(crudo)
                    except json.JSONDecodeError:
                        pass
                return crudo[1:-1]
            j += 1
    return None


def _texto_plano(bruto: str | None) -> str | None:
    if not bruto:
        return None
    t = re.sub(r"<br\s*/?>", "\n", bruto, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip() or None


def _numero(txt) -> float | None:
    if txt is None:
        return None
    m = re.search(r"[\d\.,]+", str(txt))
    if not m:
        return None
    limpio = m.group(0).replace(".", "").replace(",", ".")
    try:
        return float(limpio)
    except ValueError:
        return None


def extraer(html: str) -> dict:
    d: dict = {}

    tipo = _valor_js(html, "realEstateType") or {}
    nombre_tipo = (tipo.get("name") or "").lower()
    d["tipo"] = {"casa": "casa", "ph": "ph", "departamento": "departamento"}.get(nombre_tipo)
    d["tipo_declarado"] = tipo.get("name")

    dirn = _valor_js(html, "address") or {}
    if dirn.get("name"):
        d["direccion"] = dirn["name"]
    d["direccion_visibilidad"] = dirn.get("visibility")

    feats = _valor_js(html, "mainFeatures") or {}
    for cft, info in feats.items():
        campo = MAPA_FEATURES.get(cft)
        if not campo:
            continue
        valor = info.get("value")
        d[campo] = valor if campo in TEXTUALES else _numero(valor)

    if d.get("banos_declarados") is not None:
        d["banos_completos"] = int(d["banos_declarados"])
    if d.get("toilettes") is not None:
        d["toilettes"] = int(d["toilettes"])
    if d.get("cocheras") is not None:
        d["cochera"] = d["cocheras"] > 0
    disp = (d.get("disposicion") or "").strip().lower()
    if disp.startswith("contrafrente"):
        d["al_frente"] = False
    elif disp.startswith("frente"):
        d["al_frente"] = True

    precio_txt = _valor_js(html, "price")
    if isinstance(precio_txt, str):
        d["precio_texto"] = precio_txt
        n = _numero(precio_txt)
        if n and "usd" in precio_txt.lower():
            d["precio_alquiler_usd"] = n
            d["moneda_publicacion"] = "USD"
        elif n:
            d["precio_alquiler_ars"] = n
            d["moneda_publicacion"] = "ARS"

    # Zonaprop muestra las expensas junto al precio SOLO si existen. Se registra el hecho
    # crudo; NO se infiere "sin expensas" desde la ausencia (ver CLAUDE.md).
    m_exp = re.search(r"\$\s*([\d\.]+)\s*expensas", html, re.I)
    d["expensas_ars"] = _numero(m_exp.group(1)) if m_exp else None
    d["expensas_declaradas"] = bool(m_exp)

    pub = _valor_js(html, "publicationDateFormatted")
    if isinstance(pub, str):
        d["publicado_el"] = pub
        try:
            f = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            d["publicado_hace_dias"] = (datetime.now(timezone.utc) - f).days
        except ValueError:
            pass

    tipo_pub = _valor_js(html, "publisherTypeId")
    if tipo_pub is not None:
        d["dueno_directo"] = str(tipo_pub).strip() == "1"

    d["descripcion"] = _texto_plano(_valor_js(html, "description"))
    d["titulo"] = _texto_plano(_valor_js(html, "title")) or None

    fotos, captions = [], []
    for p in (_valor_js(html, "pictures") or []):
        u = p.get("url730x532") or p.get("url720x532") or p.get("url1200x1200")
        if not u:
            continue
        fotos.append(u.split("?")[0])
        captions.append(p.get("title"))
    d["fotos_remotas"] = fotos
    d["fotos_captions"] = captions
    return d


# --------------------------------------------------------------------------- fotos

def repartir(urls: list[str], maximo: int) -> list[str]:
    """Elige `maximo` fotos REPARTIDAS a lo largo del aviso, no las primeras.

    El anunciante ordena las fotos para vender: adelante van las lindas. Verificado en las
    tres primeras clasificaciones de este proyecto: la foto que delataba que Superi 4300
    funciona hoy como oficina era la 6 de 6, y la que confirmaba que el reciclado de
    Paroissien 4400 es real era la 5 (la cocina). Con las tres primeras no se veia ninguna
    de las dos. Tomar primera, del medio y ultima cuesta lo mismo y no deja que el
    anunciante elija que miramos.
    """
    if maximo <= 0 or not urls:
        return []
    if len(urls) <= maximo:
        return list(urls)
    paso = (len(urls) - 1) / (maximo - 1) if maximo > 1 else 0
    idx = sorted({round(i * paso) for i in range(maximo)})
    return [urls[i] for i in idx]


def bajar_fotos(aviso_id: str, urls: list[str], cfg: dict, maximo: int) -> list[str]:
    """Guarda en web/fotos/<id>/NN.jpg y devuelve rutas RELATIVAS a web/.

    Relativas a proposito: la pagina abre con file:// y con servidor local, y en los dos
    casos 'fotos/<id>/01.jpg' resuelve igual.
    """
    destino = DIR_FOTOS / aviso_id
    destino.mkdir(parents=True, exist_ok=True)
    guardadas = []
    for i, u in enumerate(repartir(urls, maximo), start=1):
        archivo = destino / f"{i:02d}.jpg"
        rel = f"fotos/{aviso_id}/{archivo.name}"
        if archivo.exists() and archivo.stat().st_size > 0:
            guardadas.append(rel)
            continue
        try:
            req = urllib.request.Request(u, headers={
                "User-Agent": cfg["rate_limit"]["user_agent"],
                "Referer": "https://www.zonaprop.com.ar/",
                "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                datos = r.read()
            if len(datos) < 800:  # placeholder o error disfrazado
                continue
            archivo.write_bytes(datos)
            guardadas.append(rel)
        except Exception:  # noqa: BLE001
            continue
        time.sleep(random.uniform(0.25, 0.6))
    return guardadas


# --------------------------------------------------------------------------- corrida

def refrescar(ids: list[str] | None = None, forzar: bool = False,
              solo_vigencia: bool = False) -> dict:
    """solo_vigencia = pedir la URL, decidir si vive, y nada mas.

    Un aviso por request, sin fotos y sin reparsear la ficha. Es lo unico que puede
    declarar una caida: no salir en un barrido no es evidencia de nada (ver reconciliar()
    en main.py). Se usa para saldar la duda de los que quedaron con ausente_veces > 0.
    """
    cfg = load_config()
    maximo = int(cfg.get("fotos", {}).get("max_por_aviso", 6))
    doc = leer_json(DIR_DATA / "avisos.json")
    hoy = date.today().isoformat()
    res = {"ok": [], "desaparecidos": [], "error": [], "fotos": 0, "cambios": []}

    for a in doc["avisos"]:
        if ids and a["id"] not in ids:
            continue
        if not a.get("url"):
            continue
        if not forzar and not solo_vigencia and a.get("ficha_leida_el") == hoy:
            continue

        try:
            html = bajar_html(a["url"], cfg)
        except Exception as e:  # noqa: BLE001
            res["error"].append({"id": a["id"], "direccion": a.get("direccion"), "error": str(e)[:120]})
            dormir(cfg)
            continue

        if html is None or any(s in html.lower() for s in SIN_AVISO):
            a["estado_aviso"] = "desaparecido"
            a["desaparecido_el"] = hoy
            a["vigencia_verificada_el"] = hoy
            res["desaparecidos"].append({"id": a["id"], "direccion": a.get("direccion"),
                                         "era_favorito": bool(a.get("pinned"))})
            dormir(cfg)
            continue

        if solo_vigencia:
            a["estado_aviso"] = "vigente"
            a["vigencia_verificada_el"] = hoy
            a["ausente_veces"] = 0
            res["ok"].append({"id": a["id"], "direccion": a.get("direccion")})
            dormir(cfg)
            continue

        datos = extraer(html)

        # Registrar que campos de la semilla cambian contra la ficha real.
        for campo in ("m2_cubiertos", "m2_totales", "dormitorios_declarados", "tipo"):
            antes, ahora = a.get(campo), datos.get(campo)
            if ahora is not None and antes is not None and antes != ahora:
                res["cambios"].append({"id": a["id"], "direccion": a.get("direccion"),
                                       "campo": campo, "antes": antes, "ahora": ahora})

        urls = datos.pop("fotos_remotas", [])
        captions = datos.pop("fotos_captions", [])
        a.update({k: v for k, v in datos.items() if v is not None})
        a["fotos"] = bajar_fotos(a["id"], urls, cfg, maximo)
        a["fotos_captions"] = captions[:len(a["fotos"])]
        a["fotos_remotas"] = urls
        a["estado_aviso"] = "vigente"
        a["last_seen"] = hoy
        a["ficha_leida_el"] = hoy
        res["fotos"] += len(a["fotos"])
        res["ok"].append({"id": a["id"], "direccion": a.get("direccion"), "fotos": len(a["fotos"])})
        dormir(cfg)

    escribir_json(DIR_DATA / "avisos.json", doc)
    return res


if __name__ == "__main__":
    argv = [x for x in sys.argv[1:] if not x.startswith("--")]
    r = refrescar(argv or None, forzar="--forzar" in sys.argv,
                  solo_vigencia="--solo-vigencia" in sys.argv)
    print(f'fichas ok: {len(r["ok"])} · fotos: {r["fotos"]} · '
          f'desaparecidos: {len(r["desaparecidos"])} · errores: {len(r["error"])}')
    for c in r["cambios"]:
        print(f'  CAMBIA {c["direccion"]}: {c["campo"]} {c["antes"]} -> {c["ahora"]}')
    for d in r["desaparecidos"]:
        print(f'  CAIDO  {d["direccion"]}' + ("  ** ERA FAVORITO **" if d["era_favorito"] else ""))
    for e in r["error"]:
        print(f'  ERROR  {e["direccion"]}: {e["error"]}')
