"""Utilidades compartidas: rutas, lectura de config.yaml y normalizacion de direcciones.

No usa dependencias externas a proposito. PyYAML no esta instalado en esta maquina y no se
instala nada sin autorizacion, asi que este modulo trae un parser del SUBSET de YAML que usa
config.yaml: mapas anidados por indentacion, listas y mapas en linea, escalares, comentarios.

Si algun dia se autoriza `pip install pyyaml`, reemplazar `load_config` por yaml.safe_load y
borrar el parser. El resto del codigo no cambia.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATA = RAIZ / "data"
DIR_WEB = RAIZ / "web"
DIR_CORRIDAS = RAIZ / "corridas"
DIR_CONOCIMIENTO = RAIZ / "conocimiento"
RUTA_CONFIG = RAIZ / "config.yaml"


# --------------------------------------------------------------------------- YAML subset

def _escalar(txt: str):
    txt = txt.strip()
    if txt == "" or txt == "~" or txt.lower() == "null":
        return None
    if txt.lower() == "true":
        return True
    if txt.lower() == "false":
        return False
    if len(txt) >= 2 and txt[0] == txt[-1] and txt[0] in "\"'":
        return txt[1:-1]
    if re.fullmatch(r"-?\d+", txt):
        return int(txt)
    if re.fullmatch(r"-?\d*\.\d+", txt):
        return float(txt)
    return txt


def _partir_en_comas(txt: str) -> list[str]:
    """Corta por comas de primer nivel, respetando corchetes, llaves y comillas."""
    partes, actual, prof, comilla = [], "", 0, None
    for ch in txt:
        if comilla:
            actual += ch
            if ch == comilla:
                comilla = None
            continue
        if ch in "\"'":
            comilla = ch
            actual += ch
        elif ch in "[{":
            prof += 1
            actual += ch
        elif ch in "]}":
            prof -= 1
            actual += ch
        elif ch == "," and prof == 0:
            partes.append(actual)
            actual = ""
        else:
            actual += ch
    if actual.strip():
        partes.append(actual)
    return partes


def _valor_en_linea(txt: str):
    txt = txt.strip()
    # Una lista que abre y no cierra en la misma linea significa que alguien la partio en
    # varias. Este parser lee linea por linea y no sabe juntarlas: si devolviera el string
    # crudo, iterar sobre el daria CARACTERES sueltos en vez de elementos. Paso de verdad:
    # una lista de barrios partida en dos lineas hizo que el barrido pidiera la busqueda
    # sin barrio (toda CABA, 476 paginas) y Zonaprop devolvio 403. Mejor romper fuerte.
    if txt.startswith("[") and not txt.endswith("]"):
        raise ValueError(f"lista YAML sin cerrar en una sola linea: {txt[:60]}... "
                         "Este parser no soporta listas multilinea; dejala en un renglon.")
    if txt.startswith("{") and not txt.endswith("}"):
        raise ValueError(f"mapa YAML sin cerrar en una sola linea: {txt[:60]}...")
    if txt.startswith("[") and txt.endswith("]"):
        cuerpo = txt[1:-1].strip()
        return [_valor_en_linea(p) for p in _partir_en_comas(cuerpo)] if cuerpo else []
    if txt.startswith("{") and txt.endswith("}"):
        cuerpo = txt[1:-1].strip()
        out = {}
        for par in _partir_en_comas(cuerpo):
            if ":" not in par:
                continue
            k, v = par.split(":", 1)
            out[k.strip().strip("\"'")] = _valor_en_linea(v)  # las claves quedan siempre como str
        return out
    return _escalar(txt)


def _sin_comentario(linea: str) -> str:
    fuera, comilla = "", None
    for ch in linea:
        if comilla:
            fuera += ch
            if ch == comilla:
                comilla = None
        elif ch in "\"'":
            comilla = ch
            fuera += ch
        elif ch == "#":
            break
        else:
            fuera += ch
    return fuera.rstrip()


def _parsear(lineas: list[tuple[int, str]], i: int, sangria: int):
    """Devuelve (valor, indice_siguiente). Soporta mapas y listas de bloque."""
    if i < len(lineas) and lineas[i][1].startswith("- "):
        items = []
        while i < len(lineas) and lineas[i][0] == sangria and lineas[i][1].startswith("- "):
            items.append(_valor_en_linea(lineas[i][1][2:]))
            i += 1
        return items, i

    mapa = {}
    while i < len(lineas):
        ind, texto = lineas[i]
        if ind < sangria:
            break
        if ind > sangria:  # bloque huerfano: lo salteamos
            i += 1
            continue
        if ":" not in texto:
            i += 1
            continue
        clave, resto = texto.split(":", 1)
        clave = clave.strip().strip("\"'")
        resto = resto.strip()
        if resto:
            mapa[clave] = _valor_en_linea(resto)
            i += 1
        else:
            if i + 1 < len(lineas) and lineas[i + 1][0] > sangria:
                sub, i = _parsear(lineas, i + 1, lineas[i + 1][0])
                mapa[clave] = sub
            else:
                mapa[clave] = None
                i += 1
    return mapa, i


def load_config(ruta: Path | None = None) -> dict:
    ruta = ruta or RUTA_CONFIG
    crudo = ruta.read_text(encoding="utf-8").splitlines()
    lineas = []
    for ln in crudo:
        limpia = _sin_comentario(ln)
        if not limpia.strip():
            continue
        lineas.append((len(limpia) - len(limpia.lstrip()), limpia.strip()))
    valor, _ = _parsear(lineas, 0, 0)
    return valor


# --------------------------------------------------------------------------- JSON

def leer_json(ruta: Path, por_defecto=None):
    if not ruta.exists():
        return por_defecto
    return json.loads(ruta.read_text(encoding="utf-8"))


def escribir_json(ruta: Path, dato) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(dato, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- direcciones

_PREFIJOS = ("av. ", "av ", "avenida ", "calle ", "cl ")


GBA_NORTE = ("vicente lopez", "san isidro", "olivos", "florida", "la lucila", "munro",
             "carapachay", "villa martelli", "martinez", "beccar", "acassuso",
             "la horqueta", "boulogne", "villa adelina")


def zonas_a_barrer(cfg: dict) -> list:
    """Lo que se le PIDE a los portales, que no es lo mismo que lo que se acepta.

    `zonas.incluidas` es la lista de ACEPTACION (la lee el duro `zona`). Para pedir hay
    una lista aparte porque en GBA se pide el PARTIDO y vuelven sus localidades: pedir
    "san-isidro" trae Martinez, Beccar y Acassuso, que tienen que estar en `incluidas`
    para pasar el filtro pero NO tienen que pedirse una por una.

    Si `zonas.barrido` no esta, se cae a `incluidas` y todo sigue como antes.
    """
    z = (cfg.get("zonas") or {}).get("barrido")
    # Misma defensa que el resto del parser: un string se itera por letra y termina
    # pidiendo el barrio "[" — que en Zonaprop es la busqueda de toda CABA. Fue el 403
    # de la sesion 4.
    if isinstance(z, str) or not z:
        z = None
    return list(z) if z else list((cfg.get("zonas") or {}).get("incluidas") or [])


def es_gba(zona: str | None) -> bool:
    """Si la zona es de GBA Zona Norte y no de CABA. Cambia la URL en MercadoLibre,
    que separa la geografia en `capital-federal` y `bsas-gba-norte/<partido>`."""
    z = (zona or "").strip().lower()
    for a, b in (("ñ", "n"), ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        z = z.replace(a, b)
    return any(g in z for g in GBA_NORTE)


def normalizar_direccion(direccion: str | None) -> str | None:
    """minusculas, sin acentos, sin 'av.', calle + altura EXACTA.

    La altura no se redondea: Conde 4700 es favorito, Conde 4400 es descarte por uso comercial
    y Conde 1985 es descarte por mascotas. Redondear vetaria las tres juntas.

    Los anunciantes pegan anotaciones a la direccion:
        "CONDE 1985. Entre Echeverria y Sucre, antonio j. de"
        "GODOY CRUZ 3213. Entre Av Libertador y ..."
    Sin cortar eso, la direccion normalizada se quedaba con media cuadra adentro, la
    altura no se podia extraer y **el veto por descarte no matcheaba**: Conde 1985 estaba
    descartado por mascotas y volvia a aparecer igual.
    """
    if not direccion:
        return None
    txt = unicodedata.normalize("NFKD", direccion.lower())
    txt = "".join(c for c in txt if not unicodedata.combining(c))

    # El punto de una ABREVIATURA DE NOMENCLATURA no es el punto que separa la anotacion.
    # Sin esto, "Av. Cabildo 2200" se partia en "av" y perdia calle y altura enteras.
    # Medido el 2026-08-23 sobre la base: 37 avisos quedaban con claves como 'av', 'dr',
    # 'tte', 'avda', 'pje' — o sea que decenas de propiedades DISTINTAS compartian clave.
    # Las dos consecuencias son malas: la deduplicacion fusionaba inmuebles que no tienen
    # nada que ver, y el veto por descarte se propagaba a todos ellos (habia un descarte
    # de "Av. Cramer 4400" con clave 'av', vetando cualquier avenida que entrara despues).
    txt = re.sub(r"\b(av|avda|avenida|dr|dra|gral|tte|cnel|pte|pres|ing|arq|pje|sgto"
                 r"|alte|brig|mons|prof|cap|sta|sto|hnos)\.\s*", r"\1 ", txt)

    # Corta la anotacion, pero NO en la inicial de un nombre: "Lidoro J. Quinteros 1100"
    # se partia en "lidoro j" y perdia calle y altura de una sola vez.
    txt = re.sub(r"\b([a-z])\.\s", r"\1 ", txt)
    txt = re.split(r"[.,;()]", txt)[0]                                  # corta la anotacion
    txt = re.split(r"\s\b(entre|esq|esquina|e/|casi)\b\s", txt)[0]      # y las calles cruce
    txt = re.sub(r"\s+", " ", txt).strip()

    for p in _PREFIJOS:
        if txt.startswith(p):
            txt = txt[len(p):]
    txt = re.sub(r"\b(al|nro|numero|n)\b\s+(?=\d)", "", txt)
    txt = re.sub(r"\s+", " ", txt).strip()

    # si quedo "calle 1234 loquesea", cortar justo despues de la altura
    m = re.match(r"^(.*?\s\d{1,5})(?:\s|$)", txt)
    return m.group(1) if m else txt


# --------------------------------------------------------------------------- numeracion

def asignar_numeros(doc: dict) -> int:
    """Da a cada aviso un numero corto y ESTABLE (#1, #2, ...). Devuelve cuantos asigno.

    Para que sirve: para que Mario pueda decir "descarta el #7" en vez de
    "descarta zp-59818437". El numero es su manija sobre el inventario.

    Reglas:
      - Se asigna una sola vez, en el orden en que el aviso aparecio (first_seen, luego id).
      - NUNCA se reasigna ni se reutiliza. Si un aviso se cae, su numero se retira con el:
        que el #7 de hoy sea otra propiedad que el #7 de ayer haria inservible cualquier
        conversacion pasada.
    """
    usados = {a["num"] for a in doc["avisos"] if isinstance(a.get("num"), int)}
    siguiente = max(usados) + 1 if usados else 1
    pendientes = [a for a in doc["avisos"] if not isinstance(a.get("num"), int)]
    pendientes.sort(key=lambda a: (a.get("first_seen") or "9999", a.get("id") or ""))
    for a in pendientes:
        a["num"] = siguiente
        siguiente += 1
    return len(pendientes)


def por_numero(doc: dict, n: int) -> dict | None:
    for a in doc["avisos"]:
        if a.get("num") == n:
            return a
    return None


def calle_y_altura(direccion_norm: str | None):
    if not direccion_norm:
        return None, None
    m = re.search(r"^(.*?)\s+(\d{1,5})$", direccion_norm)
    if not m:
        return direccion_norm, None
    return m.group(1).strip(), int(m.group(2))


# --------------------------------------------------------------------------- avenidas

# "Tranquilidad" pesa 15 y el perfil de Mario la marca PRIORITARIA, pero el campo
# `sobre_avenida` venia poblado en 1 aviso de 320: en la practica el score le daba a cada
# propiedad una constante segun el tipo (casa / ph / departamento) y no distinguia una casa
# en una calle interna de una casa sobre Cabildo. La direccion, que esta en el 100% de los
# avisos, alcanza para resolverlo gratis.
#
# DOS NIVELES A PROPOSITO. Hay nombres que en CABA son SIEMPRE avenida (Cabildo,
# Triunvirato) y otros que existen como calle y como avenida en distintos barrios
# (San Martin, Sarmiento, Independencia). Marcar `sobre_avenida = True` por un nombre
# ambiguo seria inventar un dato: se marca solo lo seguro, y lo dudoso queda en None con
# el motivo anotado, para que se pueda revisar en vez de arrastrar un error silencioso.

AVENIDAS_SEGURAS = {
    # zona norte / los barrios del perfil
    "cabildo", "triunvirato", "alvarez thomas", "elcano", "forest", "de los incas",
    "chorroarin", "constituyentes", "monroe", "congreso", "ricardo balbin", "balbin",
    "crisologo larralde", "garcia del rio", "ruiz huidobro", "olleros", "dorrego",
    "federico lacroze", "lacroze", "combatientes de malvinas", "salvador maria del carril",
    "mosconi", "lidoro quinteros", "lidoro j quinteros", "del libertador", "libertador",
    "figueroa alcorta", "intendente cantilo", "udaondo", "leopoldo lugones",
    # centro / oeste, para cuando se amplien zonas
    "corrientes", "cordoba", "santa fe", "las heras", "scalabrini ortiz", "juan b justo",
    "warnes", "nazca", "gaona", "honorio pueyrredon", "angel gallardo", "estado de israel",
    "diaz velez", "medrano", "jose maria moreno", "rivadavia", "directorio", "boyaca",
    "segurola", "alvarez jonte", "beiro", "san pedrito", "avellaneda", "la plata",
    "entre rios", "callao", "pueyrredon", "jujuy", "boedo", "saenz", "caseros",
    "paseo colon", "belgrano", "independencia", "juan de garay", "brasil",
}

# Nombres que existen como calle Y como avenida segun el tramo: no se marcan solos.
AVENIDAS_AMBIGUAS = {"san martin", "sarmiento", "santa rosa", "alberdi", "varela", "moreno"}

_RE_AV = re.compile(r"^\s*(av|avda|avenida)\b\.?\s+", re.I)


def sobre_avenida(direccion: str | None, direccion_norm: str | None = None) -> tuple[bool | None, str]:
    """(esta_sobre_avenida, motivo). None = no se puede afirmar, no "no".

    Se mira la calle YA NORMALIZADA, nunca el texto crudo: "DELGADO 600. Entre Lacroze,
    federico y Alvarez thomas" esta sobre Delgado, no sobre ninguna de las dos avenidas
    que nombra la anotacion. Es el mismo error que rompia el veto de descartados.
    """
    if not direccion:
        return None, "sin direccion"
    if _RE_AV.match(direccion.strip()):
        return True, "el aviso escribe 'Av.' delante del nombre"

    norm = direccion_norm or normalizar_direccion(direccion)
    calle, _ = calle_y_altura(norm)
    if not calle:
        return None, "no se pudo aislar la calle"
    if calle in AVENIDAS_SEGURAS:
        return True, f"{calle} es avenida en CABA"
    if calle in AVENIDAS_AMBIGUAS:
        return None, f"{calle} existe como calle y como avenida: hay que mirar el tramo"
    return False, "no figura como avenida"
