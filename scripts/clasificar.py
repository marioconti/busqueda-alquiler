"""Clasificacion de avisos con la API de Claude: texto primero, fotos despues.

DEPENDENCIA PENDIENTE DE APROBACION
-----------------------------------
Este es el UNICO script del proyecto que necesita un paquete externo:

    pip install anthropic

No esta instalado y no se instala sin autorizacion. Todo lo demas (score, build, la
pagina) corre con la biblioteca estandar. Hasta que se apruebe, este archivo es codigo
listo pero sin ejecutar.

Tambien hace falta la credencial: ANTHROPIC_API_KEY en el entorno.

ORDEN DE LOS PASOS (seccion 8 y 11 del prompt de arranque)
-----------------------------------------------------------
1. Filtro BARATO por texto sobre TODO el universo bajado.
2. Analisis VISUAL solo sobre los que pasaron los filtros duros.

Las fotos son lo mas caro. Clasificar imagenes de todo el universo es tirar plata.

CACHEO
------
En cada aviso se guarda un hash del texto de la descripcion y otro de la lista de URLs
de fotos. Se reclasifica solo si: el aviso es nuevo, cambio el hash del texto (el
anunciante edito), o cambio el set de fotos.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import DIR_DATA, escribir_json, leer_json, load_config  # noqa: E402

try:
    import anthropic
except ImportError:  # pragma: no cover - dependencia pendiente de aprobacion
    anthropic = None


# --------------------------------------------------------------------------- esquemas

def _nullable(*tipos):
    return {"anyOf": [{"type": t} for t in tipos] + [{"type": "null"}]}


def _enum_nullable(valores):
    return {"anyOf": [{"type": "string", "enum": valores}, {"type": "null"}]}


ESQUEMA_TEXTO = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "amoblado": _nullable("boolean"),
        "mascotas": _enum_nullable(["si", "no", "solo_gato", "solo_perro", "a_confirmar"]),
        "uso_permitido": _enum_nullable(["vivienda", "comercial", "ambos", "temporario"]),
        "exterior": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tipo": {"type": "string"},
                    "m2": _nullable("number"),
                    "descubierto": {"type": "boolean"},
                },
                "required": ["tipo", "m2", "descubierto"],
            },
        },
        "parrilla": _enum_nullable(["propia", "amenity", "ninguna"]),
        "banos_completos": _nullable("integer"),
        "toilettes": _nullable("integer"),
        "dormitorios_reales": _nullable("integer"),
        "m2_cubiertos": _nullable("number"),
        "m2_descubiertos": _nullable("number"),
        "estado": _enum_nullable(["a_estrenar", "reciclado", "bueno", "cosmetico", "a_refaccionar"]),
        "senales_reforma": {"type": "array", "items": {"type": "string"}},
        "senales_antiguedad": {"type": "array", "items": {"type": "string"}},
        "unidades_en_el_edificio": _nullable("integer"),
        "entrada_independiente": _nullable("boolean"),
        "sobre_avenida": _nullable("boolean"),
        "garantias_aceptadas": {"type": "array", "items": {"type": "string"}},
        "deposito_meses": _nullable("number"),
        "contrato_meses": _nullable("integer"),
        "ajuste": _nullable("string"),
        "moneda": _enum_nullable(["ARS", "USD"]),
        "abl": _enum_nullable(["inquilino", "propietario"]),
        "aysa": _enum_nullable(["inquilino", "propietario"]),
        "disponibilidad": _nullable("string"),
        "fotos_generadas_con_ia": {"type": "boolean"},
        "aviso_de_prueba": {"type": "boolean"},
        "observacion": _nullable("string"),
    },
    "required": [
        "amoblado", "mascotas", "uso_permitido", "exterior", "parrilla", "banos_completos",
        "toilettes", "dormitorios_reales", "m2_cubiertos", "m2_descubiertos", "estado",
        "senales_reforma", "senales_antiguedad", "unidades_en_el_edificio",
        "entrada_independiente", "sobre_avenida", "garantias_aceptadas", "deposito_meses",
        "contrato_meses", "ajuste", "moneda", "abl", "aysa", "disponibilidad",
        "fotos_generadas_con_ia", "aviso_de_prueba", "observacion",
    ],
}

ESQUEMA_FOTOS = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "estado_visual": _enum_nullable(["a_estrenar", "reciclado", "bueno", "cosmetico", "a_refaccionar"]),
        "decada_estimada_ultima_reforma": _nullable("string"),
        "cocina": _nullable("string"),
        "banos": _nullable("string"),
        "terraza_m2_estimados": _nullable("number"),
        "terraza_utilizable": _nullable("boolean"),
        "banderas_rojas": {"type": "array", "items": {"type": "string"}},
        "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
    },
    "required": [
        "estado_visual", "decada_estimada_ultima_reforma", "cocina", "banos",
        "terraza_m2_estimados", "terraza_utilizable", "banderas_rojas", "confianza",
    ],
}


# --------------------------------------------------------------------------- prompts

PROMPT_TEXTO = """Sos un tasador que lee avisos de alquiler de CABA y extrae datos duros.

REGLAS QUE NO SE NEGOCIAN:

1. NO ESTIMES SUPERFICIES QUE EL AVISO NO DECLARA. Si no dice los m2 de la terraza,
   el campo va en null. Un numero inventado contamina todo el ranking.
2. EL SILENCIO SOBRE EL ESTADO ES null, NO "bueno". Un aviso de 200 m2 que no dice una
   sola palabra del estado es la peor senal de todas; no lo premies con un valor neutro.
3. NO CUENTES ESCRITORIOS, ENTREPISOS, PLAYROOMS NI DEPENDENCIAS DE SERVICIO COMO
   DORMITORIOS, aunque el aviso los sume en los "ambientes". El campo dormitorios_reales
   es lo que realmente se puede usar para dormir.
4. Un toilette no es un bano completo. Van en campos distintos.

VOCABULARIO (es un codigo, usalo):

- Reforma real: "reciclado a nuevo", "refaccionado por completo", "a estrenar",
  "re acondicionada a nuevo", o marcas y materiales concretos (Silestone, Ferrum, DVH,
  doble vidrio, porcelanato, aberturas nuevas, termotanque nuevo, instalacion electrica
  nueva). -> senales_reforma
- Maquillaje sobre estructura vieja: "recien pintado", "impecable", "muy bien
  conservado", "conserva sus pisos originales de pinotea", "mantiene el encanto de
  epoca", "estado bueno de epoca", "pinotea plastificada". -> estado = "cosmetico",
  y la frase a senales_antiguedad.
- Antiguedad sin declarar: dependencia de servicio, tiro balanceado, calefon, mosaico
  calcareo, "primer piso por escalera", jacuzzi. -> senales_antiguedad
- Dueno que no quiere alquilar de verdad: "posibilidad de local comercial o terreno para
  construir", "apto todo destino", contrato de un solo ano, "tambien a la venta".
  -> observacion

OTROS CAMPOS:

- mascotas: "a_confirmar" si el aviso no dice nada. "solo_perro" si acepta perros pero
  no gatos (eso es un rechazo, no una duda).
- aviso_de_prueba: true si contiene "ficticia", "de prueba", "tokko broker",
  "no contactar", o declara mas de 2000 m2 totales.
- fotos_generadas_con_ia: true si el aviso aclara que las imagenes fueron creadas o
  editadas con IA.
- disponibilidad: la fecha desde la que se puede ocupar, si el aviso la declara
  ("libre desde septiembre", "disponible a partir del 1 de octubre").

Devolve solo los datos que el aviso respalda. Ante la duda, null."""

PROMPT_FOTOS = """Sos un arquitecto mirando las fotos de un aviso de alquiler.

El paso de fotos existe para hacer dos cosas que el texto no puede: (a) determinar el
estado REAL, no el declarado, y (b) estimar la superficie de terraza cuando el aviso no
la declara. Son las dos que mas pesan en la decision.

- estado_visual: lo que ves, no lo que el aviso dice. Buscá humedad, revoque flojo,
  carpinteria vieja, instalacion a la vista, pisos originales sin reformar, banos y
  cocinas de decada anterior.
- decada_estimada_ultima_reforma: aproximada, en base a griferia, azulejos, mesadas,
  aberturas. Un jacuzzi delata un reciclado de los 2000.
- terraza_m2_estimados: estimala comparando contra objetos de escala conocida (baldosas,
  una silla, una mesa, una parrilla). Si no hay foto de exterior, null.
- terraza_utilizable: false si esta sin impermeabilizar, si tiene tanques de agua,
  tendederos fijos, maquinas de aire acondicionado o esta ocupada por instalaciones.
  Una terraza que no se puede caminar y llenar de plantas no sirve.
- banderas_rojas: problemas constructivos concretos y visibles.
- confianza: "baja" si hay pocas fotos, si son borrosas, si no muestran los ambientes
  principales, o si el aviso declaro que las imagenes fueron generadas con IA.

No inventes lo que no se ve en las fotos."""


# --------------------------------------------------------------------------- helpers

def hash_texto(txt: str | None) -> str | None:
    return hashlib.sha256((txt or "").encode("utf-8")).hexdigest()[:16] if txt else None


def hash_fotos(urls: list[str] | None) -> str | None:
    if not urls:
        return None
    return hashlib.sha256("|".join(urls).encode("utf-8")).hexdigest()[:16]


def necesita_texto(aviso: dict) -> bool:
    return aviso.get("hash_texto") != hash_texto(aviso.get("descripcion"))


def necesita_fotos(aviso: dict) -> bool:
    return aviso.get("hash_fotos") != hash_fotos(aviso.get("fotos"))


def _bajar_imagen(url: str, timeout: int = 20):
    """Devuelve (media_type, base64) o None. Sin dependencias externas."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        crudo = r.read()
        media = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    if media not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        media = "image/jpeg"
    return media, base64.standard_b64encode(crudo).decode("ascii")


def _acumular_costo(uso, acumulador: dict) -> None:
    acumulador["entrada"] += getattr(uso, "input_tokens", 0) or 0
    acumulador["salida"] += getattr(uso, "output_tokens", 0) or 0
    acumulador["cache_lectura"] += getattr(uso, "cache_read_input_tokens", 0) or 0
    acumulador["cache_escritura"] += getattr(uso, "cache_creation_input_tokens", 0) or 0
    acumulador["llamadas"] += 1


def _json_de(respuesta) -> dict:
    for bloque in respuesta.content:
        if bloque.type == "text":
            return json.loads(bloque.text)
    raise ValueError("la respuesta no trajo ningun bloque de texto")


# --------------------------------------------------------------------------- API

def clasificar_texto(client, aviso: dict, cfg: dict, costo: dict) -> dict:
    api = cfg.get("api", {})
    cuerpo = "\n\n".join(filter(None, [
        f'TITULO: {aviso.get("titulo") or ""}',
        f'BARRIO DECLARADO: {aviso.get("barrio") or ""}',
        f'DESCRIPCION:\n{aviso.get("descripcion") or ""}',
    ]))
    r = client.messages.create(
        model=api.get("modelo_texto", "claude-opus-5"),
        max_tokens=int(api.get("max_tokens", 16000)),
        system=PROMPT_TEXTO,
        output_config={
            "effort": api.get("effort_texto", "low"),
            "format": {"type": "json_schema", "schema": ESQUEMA_TEXTO},
        },
        messages=[{"role": "user", "content": cuerpo}],
    )
    _acumular_costo(r.usage, costo)
    return _json_de(r)


def clasificar_fotos(client, aviso: dict, cfg: dict, costo: dict) -> dict | None:
    api = cfg.get("api", {})
    urls = (aviso.get("fotos") or [])[: int(api.get("fotos_por_aviso", 4))]
    if not urls:
        return None

    contenido = []
    for u in urls:
        try:
            media, b64 = _bajar_imagen(u)
        except Exception:
            continue
        contenido.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}})
    if not contenido:
        return None

    contenido.append({"type": "text", "text":
                      f'Aviso: {aviso.get("direccion")}, {aviso.get("barrio")}. '
                      f'Declara {aviso.get("m2_cubiertos")} m2 cubiertos y estado '
                      f'"{aviso.get("estado")}". Evaluá las fotos.'})

    r = client.messages.create(
        model=api.get("modelo_fotos", "claude-opus-5"),
        max_tokens=int(api.get("max_tokens", 16000)),
        system=PROMPT_FOTOS,
        output_config={
            "effort": api.get("effort_fotos", "medium"),
            "format": {"type": "json_schema", "schema": ESQUEMA_FOTOS},
        },
        messages=[{"role": "user", "content": contenido}],
    )
    _acumular_costo(r.usage, costo)
    return _json_de(r)


# --------------------------------------------------------------------------- orquestacion

def correr(solo_texto: bool = False) -> dict:
    if anthropic is None:
        raise SystemExit("Falta el paquete 'anthropic'. Pedir autorizacion antes de instalarlo.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno.")

    cfg = load_config()
    doc = leer_json(DIR_DATA / "avisos.json")
    client = anthropic.Anthropic()
    costo = {"entrada": 0, "salida": 0, "cache_lectura": 0, "cache_escritura": 0, "llamadas": 0}
    pausa = float(cfg.get("rate_limit", {}).get("pausa_segundos_min", 2))

    # ---- paso 1: texto, sobre todo el universo (barato)
    for a in doc["avisos"]:
        if not a.get("descripcion") or not necesita_texto(a):
            continue
        datos = clasificar_texto(client, a, cfg, costo)
        a.update(datos)
        a["hash_texto"] = hash_texto(a.get("descripcion"))
        a["confianza_texto"] = "alta"
        time.sleep(pausa)

    # ---- paso 2: fotos, SOLO sobre los que pasaron los duros
    if not solo_texto:
        from score import evaluar_duros  # import tardio: score importa config, no la API

        for a in doc["avisos"]:
            if not necesita_fotos(a):
                continue
            duros = evaluar_duros(a, cfg)
            if not (duros["pasa"] or duros["al_limite"] or a.get("pinned")):
                continue
            visual = clasificar_fotos(client, a, cfg, costo)
            if not visual:
                continue
            a["estado_visual"] = visual.get("estado_visual")
            a["confianza_visual"] = visual.get("confianza")
            a["analisis_visual"] = visual
            a["hash_fotos"] = hash_fotos(a.get("fotos"))
            # La estimacion de terraza por fotos es uno de los dos motivos por los que
            # este paso existe: se usa solo si el aviso no declaro los m2.
            est = visual.get("terraza_m2_estimados")
            if est and not any((x.get("m2") for x in (a.get("exterior") or []))):
                a.setdefault("exterior", []).append(
                    {"tipo": "terraza", "m2": est, "descubierto": True, "nota": "estimado por fotos"}
                )
            time.sleep(pausa)

    escribir_json(DIR_DATA / "avisos.json", doc)
    return costo


# ------------------------------------------------------- transporte 2: EN SESION (gratis)
#
# Todo lo de arriba (esquemas, prompts, hashes, orden de pasos) sigue valiendo. Lo unico
# que cambiaba con la API era el TRANSPORTE: quien mira las fotos. La API cuesta creditos
# que no hay. Estas dos ordenes hacen el mismo trabajo usando la sesion de Claude Code, que
# ya esta paga:
#
#     python scripts/clasificar.py pendientes            -> arma el lote y lista las fotos
#     (Claude mira las fotos en la sesion y escribe el JSON)
#     python scripts/clasificar.py aplicar <archivo>     -> valida y guarda
#
# POR QUE UN ARCHIVO APARTE Y NO avisos.json: `data/clasificacion_visual.json` es un juicio
# nuestro, no un dato scrapeado. Si viviera en avisos.json, el proximo barrido lo pisaria y
# se perderia el trabajo de mirar. Con el hash de fotos guardado al lado, ademas, se sabe
# cuando hay que volver a mirar: solo si el anunciante cambio las fotos.

RUTA_VISUAL = DIR_DATA / "clasificacion_visual.json"

VALORES_ESTADO = ["a_estrenar", "reciclado", "bueno", "cosmetico", "a_refaccionar"]


def _leer_visual() -> dict:
    return leer_json(RUTA_VISUAL, {
        "meta": {
            "version": 1,
            "por_que_archivo_aparte": (
                "Juicio propio sobre las fotos, no dato scrapeado. Vive aparte para que un "
                "re-scrapeo no lo pise. build.py lo fusiona ANTES de puntuar."),
            "origen": "sesion de Claude Code (sin API, sin costo)",
        },
        "por_id": {},
    })


def pendientes(n: int = 12, incluir_sin_fotos: bool = False) -> dict:
    """Arma el lote de trabajo: que mirar, en que orden y donde estan las fotos."""
    from score import evaluar_duros  # import tardio, igual que en correr()

    cfg = load_config()
    doc = leer_json(DIR_DATA / "avisos.json")
    ya = _leer_visual()["por_id"]

    lote = []
    for a in doc["avisos"]:
        duros = evaluar_duros(a, cfg)
        if not (duros["pasa"] or duros["al_limite"] or a.get("pinned")):
            continue
        if a.get("decision") == "descartado":
            continue
        previo = ya.get(a["id"])
        if previo and previo.get("hash_fotos") == hash_fotos(a.get("fotos")):
            continue                              # ya mirado y las fotos no cambiaron
        fotos = a.get("fotos") or []
        if not fotos and not incluir_sin_fotos:
            continue                              # sin fotos locales no hay nada que mirar
        lote.append({
            "id": a["id"], "num": a.get("num"), "direccion": a.get("direccion"),
            "barrio": a.get("barrio"), "tipo": a.get("tipo"),
            "precio_usd": a.get("precio_total_usd"),
            "score_piso": a.get("score"),
            "estado_declarado": a.get("estado"),
            "m2_cubiertos": a.get("m2_cubiertos"), "m2_descubiertos": a.get("m2_descubiertos"),
            "exterior_declarado_m2": a.get("exterior_m2_total"),
            "fotos": fotos,
            "hash_fotos": hash_fotos(fotos),
            "url": a.get("url"),
        })

    # Primero lo que mas cerca esta de decidirse: score piso mas alto.
    lote.sort(key=lambda x: -(x["score_piso"] or 0))
    lote = lote[:n]

    salida = {
        "generado": time.strftime("%Y-%m-%d"),
        "como_completar": (
            "Para cada item: mirar las fotos de 'fotos' y agregar el objeto 'visual' con las "
            "claves de ESQUEMA_FOTOS (estado_visual, decada_estimada_ultima_reforma, cocina, "
            "banos, terraza_m2_estimados, terraza_utilizable, banderas_rojas, confianza). "
            "Guardar y correr: python scripts/clasificar.py aplicar <archivo>"),
        "criterio": PROMPT_FOTOS,
        "items": lote,
    }
    escribir_json(DIR_DATA / "pendientes_clasificacion.json", salida)
    return salida


def _validar(v: dict, ident: str) -> dict:
    """Valida a mano contra ESQUEMA_FOTOS. Sin esto, un typo entra como dato bueno."""
    if not isinstance(v, dict):
        raise SystemExit(f"{ident}: 'visual' tiene que ser un objeto")
    est = v.get("estado_visual")
    if est is not None and est not in VALORES_ESTADO:
        raise SystemExit(f"{ident}: estado_visual={est!r} no esta en {VALORES_ESTADO}")
    conf = v.get("confianza")
    if conf not in ("alta", "media", "baja"):
        raise SystemExit(f"{ident}: confianza={conf!r} tiene que ser alta/media/baja")
    m2 = v.get("terraza_m2_estimados")
    if m2 is not None and not isinstance(m2, (int, float)):
        raise SystemExit(f"{ident}: terraza_m2_estimados tiene que ser numero o null")
    banderas = v.get("banderas_rojas") or []
    if not isinstance(banderas, list):
        raise SystemExit(f"{ident}: banderas_rojas tiene que ser una lista")
    return {
        "estado_visual": est,
        "decada_estimada_ultima_reforma": v.get("decada_estimada_ultima_reforma"),
        "cocina": v.get("cocina"),
        "banos": v.get("banos"),
        "terraza_m2_estimados": m2,
        "terraza_utilizable": v.get("terraza_utilizable"),
        "banderas_rojas": banderas,
        "confianza": conf,
    }


def aplicar_lote(ruta: str | Path) -> dict:
    doc_in = leer_json(Path(ruta))
    if not doc_in or "items" not in doc_in:
        raise SystemExit(f"{ruta}: no tiene 'items'")
    store = _leer_visual()
    n = 0
    for it in doc_in["items"]:
        if not it.get("visual"):
            continue
        ident = f"#{it.get('num')} {it.get('direccion')}"
        store["por_id"][it["id"]] = {
            **_validar(it["visual"], ident),
            "hash_fotos": it.get("hash_fotos"),
            "clasificado_el": time.strftime("%Y-%m-%d"),
            "origen": "sesion",
        }
        n += 1
    store["meta"]["actualizado"] = time.strftime("%Y-%m-%d")
    escribir_json(RUTA_VISUAL, store)
    return {"aplicados": n, "total_en_store": len(store["por_id"])}


def fusionar_en(avisos: list[dict]) -> int:
    """Vuelca el store sobre los avisos. Lo llama build.py ANTES de puntuar."""
    store = _leer_visual()["por_id"]
    n = 0
    for a in avisos:
        v = store.get(a["id"])
        if not v:
            continue
        a["estado_visual"] = v.get("estado_visual")
        a["confianza_visual"] = v.get("confianza")
        a["analisis_visual"] = v
        a["hash_fotos"] = v.get("hash_fotos")
        # Se usa la estimacion de terraza SOLO si el aviso no declaro los m2, igual que
        # en el camino por API: la prosa exagera, pero el dato estructurado manda.
        est = v.get("terraza_m2_estimados")
        if est and a.get("m2_descubiertos") is None and not any(
                (x.get("m2") for x in (a.get("exterior") or []))):
            a.setdefault("exterior", []).append(
                {"tipo": "terraza", "m2": est, "descubierto": True, "nota": "estimado por fotos"})
        n += 1
    return n


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "pendientes":
        cuantos = int(args[1]) if len(args) > 1 and args[1].isdigit() else 12
        r = pendientes(cuantos, incluir_sin_fotos="--sin-fotos" in args)
        print(f'{len(r["items"])} para mirar -> data/pendientes_clasificacion.json\n')
        for it in r["items"]:
            print(f'#{it["num"]:<5}{str(it["direccion"])[:32]:<34}{len(it["fotos"])} fotos  piso {it["score_piso"]}')
    elif args and args[0] == "aplicar":
        if len(args) < 2:
            raise SystemExit("uso: python scripts/clasificar.py aplicar <archivo.json>")
        print(aplicar_lote(args[1]))
    elif args and args[0] == "api":
        c = correr(solo_texto="--solo-texto" in args)
        print(f'{c["llamadas"]} llamadas · entrada {c["entrada"]} tok · salida {c["salida"]} tok')
    else:
        print("uso: python scripts/clasificar.py pendientes [N] [--sin-fotos]")
        print("     python scripts/clasificar.py aplicar <archivo.json>")
        print("     python scripts/clasificar.py api            (necesita creditos, hoy no se usa)")
