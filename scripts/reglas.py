"""Clasificacion deterministica por vocabulario. Sin API, sin dependencias, sin costo.

POR QUE EXISTE
--------------
El vocabulario de la seccion 6 del perfil ES un conjunto de reglas de texto: "recien
pintado" significa una cosa, "reciclado a nuevo" significa otra. Eso no necesita un
modelo. Lo que si necesita un modelo es la nuance (leer una descripcion larga y decidir
si el tercer dormitorio es un escritorio) y sobre todo las FOTOS.

Entonces el orden es:

    reglas.py   (gratis, deterministico)  -> resuelve los binarios: amoblado, mascotas,
                                             uso, y una primera lectura del estado
    clasificar.py (API, cuesta)           -> resuelve la nuance y las fotos

Este modulo NUNCA pisa un campo que ya haya puesto la API (`confianza_texto == "alta"`).
Marca lo suyo como `confianza_texto: "reglas"` para que se vea de donde salio cada dato.

LIMITE HONESTO: esto lee palabras, no entiende. Un aviso que dice "no se permiten
mascotas en el edificio pero el propietario hace excepciones" lo va a leer mal. Por eso
todo lo que decide aca queda marcado y es pisable por la pasada de API.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import DIR_DATA, escribir_json, leer_json, sobre_avenida  # noqa: E402


def _norm(txt: str | None) -> str:
    if not txt:
        return ""
    t = unicodedata.normalize("NFKD", txt.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t)


def _alguna(txt: str, frases: tuple[str, ...]) -> list[str]:
    """Match por PALABRA COMPLETA, no por substring.

    Bug real que costo encontrar: buscando "vacio" como substring, "conservacion" daba
    positivo (conser-VACIO-n) y dos avisos quedaron marcados como "se entrega vacio".
    Con \\b eso no pasa.
    """
    return [f for f in frases if re.search(r"\b" + re.escape(f) + r"\b", txt)]


# --------------------------------------------------------------------------- vocabulario

REFORMA_REAL = (
    "reciclado a nuevo", "reciclada a nuevo", "refaccionado por completo",
    "refaccionada por completo", "a estrenar", "listo para re-estrenar",
    "re acondicionada a nuevo", "re acondicionado a nuevo", "totalmente reciclado",
    "totalmente reciclada", "silestone", "ferrum", "dvh", "doble vidrio", "porcelanato",
    "aberturas nuevas", "termotanque nuevo", "instalacion electrica nueva",
    "instalacion nueva", "cocina nueva", "bano nuevo", "banos nuevos",
)

MAQUILLAJE = (
    "recien pintado", "recien pintada", "impecable", "muy bien conservado",
    "muy bien conservada", "bien conservado", "bien conservada", "pisos originales",
    "pinotea", "encanto de epoca", "estado bueno de epoca", "de epoca",
    "recien plastificados", "plastificados y pulidos", "maderas originales",
    "conserva sus pisos",
)

ANTIGUEDAD = (
    "dependencia de servicio", "tiro balanceado", "calefon", "mosaico calcareo",
    "calcareos", "primer piso por escalera", "jacuzzi", "casa antigua", "casa chorizo",
)

A_REFACCIONAR = (
    "a refaccionar", "para refaccionar", "a reciclar", "para reciclar",
    "potencial de reciclaje", "a reformar", "para reformar", "necesita refaccion",
    "apto refaccion", "para demoler",
)

# OJO con las ambiguas. Se sacaron a proposito:
#   "equipado/equipada" -> "cocina equipada" es la lectura dominante, no el inmueble.
#   "con muebles"       -> "cocina completa con muebles nuevos" = bajo mesada, no ajuar.
#   "vacio"             -> ademas de ambigua, hacia falso positivo dentro de "conservacion".
# Las tres marcaban como amoblados a favoritos que no lo son.
AMOBLADO_SI = (
    "amoblado", "amoblada", "amueblado", "amueblada", "se entrega amoblado",
    "totalmente amoblado", "totalmente amoblada", "apto airbnb",
    "listo para ingresar con tu valija", "con todos los muebles", "incluye muebles",
)
AMOBLADO_NO = (
    "sin muebles", "sin amoblar", "no amoblado", "no amoblada",
    "se alquila sin muebles", "se entrega sin muebles", "desamoblado",
)

# El aviso casi nunca dice "mascotas": dice PERROS, o dice ANIMALES. Caso real que se
# colo el 2026-08-21: Caldas 1760 (#282) publica "no se permiten perros segun reglamento"
# y quedaba en `a_confirmar`, o sea pasaba el duro y entraba como candidato. El
# vocabulario tiene que cubrir la palabra que usa el anunciante, no la que usa el perfil.
MASCOTAS_NO = (
    "no acepta mascotas", "no se aceptan mascotas", "no admite mascotas",
    "no se admiten mascotas", "sin mascotas", "no mascotas", "prohibido mascotas",
    "no se permiten mascotas", "no apto mascotas", "no apto para mascotas",
    "no se permiten perros", "no permiten perros", "no se aceptan perros",
    "no se admiten perros", "no acepta perros", "no admite perros", "sin perros",
    "prohibido perros", "no se permiten animales", "no se aceptan animales",
    "no se admiten animales", "no admite animales", "prohibido animales",
)
MASCOTAS_SI = (
    "apto mascotas", "acepta mascotas", "se aceptan mascotas", "admite mascotas",
    "se admiten mascotas", "pet friendly", "apto para mascotas",
)
SOLO_PERRO = ("no gatos", "no se aceptan gatos", "perros chicos", "solo perros")

USO_COMERCIAL_EXCLUSIVO = (
    "uso comercial exclusivo", "solo uso comercial", "exclusivamente comercial",
    "apto profesional exclusivamente", "solo apto profesional", "unicamente comercial",
    "no apto vivienda", "no apto para vivienda",
)
USO_COMERCIAL_TAMBIEN = (
    "uso comercial", "apto comercial", "apto profesional", "apto todo destino",
    "todo destino", "apto oficina", "especial productoras", "distrito audiovisual",
    "apto local",
)
USO_TEMPORARIO = ("alquiler temporario", "temporario", "por temporada", "airbnb")

DUENO_NO_QUIERE = (
    "posibilidad de local comercial", "terreno para construir", "apto todo destino",
    "tambien a la venta", "tambien en venta", "se vende",
)

BASURA = ("ficticia", "ficticias", "de prueba", "tokko broker", "no contactar")
FOTOS_IA = ("generadas con inteligencia artificial", "creadas con ia", "editadas con ia",
            "imagenes generadas con", "renders con inteligencia artificial")

SIN_PORTERO = ("sin portero", "sin encargado", "no tiene portero", "no tiene encargado",
               "sin expensas", "no paga expensas", "sin gastos comunes")
CON_PORTERO = ("portero", "encargado permanente", "encargado", "porteria", "seguridad 24")

PARRILLA = ("parrilla",)
PARRILLA_COMUN = ("parrilla comun", "parrilla del edificio", "sum con parrilla", "amenities")


# --------------------------------------------------------------------------- clasificacion

def clasificar(aviso: dict) -> dict:
    """Devuelve solo los campos que las reglas pueden justificar."""
    txt = _norm(" ".join(filter(None, [aviso.get("titulo"), aviso.get("descripcion")])))
    if not txt:
        return {}

    d: dict = {"confianza_texto": "reglas"}

    if _alguna(txt, BASURA):
        d["aviso_de_prueba"] = True
    if _alguna(txt, FOTOS_IA):
        d["fotos_generadas_con_ia"] = True

    # --- amoblado (los negativos ganan: "se alquila sin muebles" contiene "muebles")
    # Se emite SIEMPRE, incluido el None: si no se emitiera, un valor equivocado de una
    # corrida anterior sobreviviria a la correccion de la regla que lo produjo.
    neg, pos = _alguna(txt, AMOBLADO_NO), _alguna(txt, AMOBLADO_SI)
    d["amoblado"] = False if neg else (True if pos else None)

    # --- mascotas
    if _alguna(txt, SOLO_PERRO):
        d["mascotas"] = "solo_perro"
    elif _alguna(txt, MASCOTAS_NO):
        d["mascotas"] = "no"
    elif _alguna(txt, MASCOTAS_SI):
        d["mascotas"] = "si"
    else:
        d["mascotas"] = "a_confirmar"

    # --- uso
    if _alguna(txt, USO_COMERCIAL_EXCLUSIVO):
        d["uso_permitido"] = "comercial"
    elif _alguna(txt, USO_TEMPORARIO) and "no temporario" not in txt:
        d["uso_permitido"] = "temporario"
    elif _alguna(txt, USO_COMERCIAL_TAMBIEN):
        d["uso_permitido"] = "ambos"
    else:
        d["uso_permitido"] = "vivienda"

    # --- estado, con la escalera del vocabulario
    reforma = _alguna(txt, REFORMA_REAL)
    maquillaje = _alguna(txt, MAQUILLAJE)
    antiguedad = _alguna(txt, ANTIGUEDAD)
    refaccionar = _alguna(txt, A_REFACCIONAR)

    d["senales_reforma"] = reforma
    d["senales_antiguedad"] = sorted(set(maquillaje + antiguedad))

    if refaccionar:
        d["estado"] = "a_refaccionar"
    elif reforma and maquillaje:
        # Declara reforma Y maquillaje a la vez: el vendedor esta vendiendo pintura como
        # obra. No se premia con "reciclado"; queda en "bueno" y lo resuelven las fotos.
        d["estado"] = "bueno"
        d["estado_ambiguo"] = True
    elif reforma:
        d["estado"] = "reciclado"
    elif maquillaje:
        d["estado"] = "cosmetico"
    elif not any(p in txt for p in ("estado", "condicion", "reciclad", "refaccion",
                                    "estrenar", "reformad", "nuevo", "nueva")):
        d["estado"] = None          # el aviso no dice NADA: el silencio penaliza (20)
        d["estado_por_silencio"] = True

    # --- a estrenar por antiguedad declarada (dato del portal, no del texto)
    ant = aviso.get("antiguedad_anios")
    if ant is not None and ant <= 2 and d.get("estado") in (None, "bueno"):
        d["estado"] = "a_estrenar"
        d["estado_ambiguo"] = False

    # --- parrilla
    if _alguna(txt, PARRILLA):
        d["parrilla"] = "amenity" if _alguna(txt, PARRILLA_COMUN) else "propia"

    # --- toilettes: el portal YA los separa de los banos (CFT4 vs CFT3), asi que el texto
    # solo se usa cuando el aviso no declara el campo. Restarlos de los banos, como hacia
    # la primera version, contaba doble.
    if aviso.get("toilettes") is None:
        m_toi = len(re.findall(r"\btoile?te?t?e?\b", txt))
        if m_toi:
            d["toilettes"] = m_toi
    if aviso.get("banos_completos") is None and aviso.get("banos_declarados") is not None:
        d["banos_completos"] = int(aviso["banos_declarados"])

    # --- portero / encargado. Interesa por las expensas: el sueldo del encargado es su
    # renglon mas grande, y Mario puso techo en USD 200. Los negativos ganan porque
    # "sin portero" contiene "portero".
    if _alguna(txt, SIN_PORTERO):
        d["portero"] = False
    elif _alguna(txt, CON_PORTERO):
        d["portero"] = True
    else:
        d["portero"] = None

    # --- senales de que el dueno no quiere alquilar de verdad
    alertas = _alguna(txt, DUENO_NO_QUIERE)
    if alertas:
        d["alertas_intencion"] = alertas

    return d


CUARTOS_QUE_NO_CUENTAN = (r"\bescritorio\b", r"\bentrepiso\b", r"\bplayroom\b",
                          r"\bdependencia de servicio\b", r"\bcuarto de servicio\b",
                          r"\bcuarto de servicio\b", r"\bestudio\b")


def _riesgo_dormitorios(aviso: dict) -> list[str]:
    """El campo `dorm.` del portal miente, pero las reglas NO pueden corregirlo.

    Primera version de esto restaba 1 por cada palabra encontrada y dejaba a Superi 4300
    con 1 dormitorio: el aviso nombra un escritorio y un playroom, pero son cuartos
    ADEMAS de los 3 dormitorios, no en lugar de ellos. Restar a ciegas destruye el dato.

    Entonces: no se toca el numero, se marca el riesgo y lo resuelve la pasada de fotos
    y texto de la API, que si puede leer la distribucion.
    """
    txt = _norm(aviso.get("descripcion"))
    return [p.strip("\\b") for p in CUARTOS_QUE_NO_CUENTAN if re.search(p, txt)]


def aplicar() -> dict:
    doc = leer_json(DIR_DATA / "avisos.json")
    res = {"clasificados": 0, "sin_texto": 0, "avenida": 0, "detalle": []}
    for a in doc["avisos"]:
        # La avenida se resuelve SIEMPRE, aunque el aviso ya lo haya resuelto un modelo:
        # esto no es una lectura de prosa sino un hecho sobre la direccion, y la direccion
        # esta en el 100% de los avisos. Es la unica excepcion a "las reglas no pisan".
        av, motivo = sobre_avenida(a.get("direccion"), a.get("direccion_norm"))
        a["sobre_avenida"] = av
        a["sobre_avenida_motivo"] = motivo
        if av:
            res["avenida"] += 1

        if a.get("confianza_texto") == "alta":
            continue  # el resto ya lo resolvio la API; las reglas no pisan
        d = clasificar(a)
        if not d:
            res["sin_texto"] += 1
            continue
        a.update(d)
        if a.get("dormitorios_declarados") is not None:
            a["dormitorios_reales"] = int(a["dormitorios_declarados"])
        riesgo = _riesgo_dormitorios(a)
        if riesgo:
            a["dormitorios_a_verificar"] = riesgo
        # superficie descubierta como proxy de exterior (regla de conocimiento/zonaprop.md)
        tot, cub = a.get("m2_totales"), a.get("m2_cubiertos")
        if tot is not None and cub is not None:
            desc = round(float(tot) - float(cub), 1)
            # UN EXTERIOR NEGATIVO NO EXISTE: si totales < cubiertos, el portal se
            # contradice a si mismo y el numero no se puede usar. Medido el 2026-08-25:
            # 43 avisos en base, con casos como m2_totales=7 sobre m2_cubiertos=52.
            # Se deja en None A PROPOSITO, no en 0. Un 0 es "medimos y no tiene
            # exterior", y el exterior es el criterio de MAYOR peso (25): afirmarlo con
            # datos rotos hunde un aviso que quiza tiene el jardin mas grande de la
            # lista. None es "no lo sabemos" y score.py lo marca "a preguntar", que es
            # la verdad. Es la misma distincion que estado=null vs sin_clasificar.
            # OJO: argenprop.py:192 y mercadolibre.py:263 hacen max(0.0, ...) sobre lo
            # mismo. No molesta porque esta pasada corre DESPUES y sobre todos los
            # portales, asi que el valor que queda es este.
            a["m2_descubiertos"] = None if desc < 0 else desc
            a["m2_descubiertos_derivado"] = True
            declarados = [x.get("m2") for x in (a.get("exterior") or []) if x.get("m2")]
            if declarados and abs(sum(declarados) - a["m2_descubiertos"]) > 15:
                a["discrepancia_exterior"] = (
                    f'el aviso declara {sum(declarados):.0f} m2 de exterior pero el portal '
                    f'informa {a["m2_descubiertos"]:.0f} m2 descubiertos')
        res["clasificados"] += 1
        res["detalle"].append({
            "direccion": a.get("direccion"), "estado": a.get("estado"),
            "amoblado": a.get("amoblado"), "mascotas": a.get("mascotas"),
            "uso": a.get("uso_permitido"), "dorm": a.get("dormitorios_reales"),
            "desc_m2": a.get("m2_descubiertos"),
        })
    escribir_json(DIR_DATA / "avisos.json", doc)
    return res


if __name__ == "__main__":
    r = aplicar()
    print(f'{r["clasificados"]} clasificados por reglas · {r["sin_texto"]} sin texto\n')
    print(f'{"propiedad":24s}{"estado":13s}{"amobl":7s}{"mascotas":13s}{"uso":11s}{"dorm":5s}{"m2 desc":>8s}')
    for x in r["detalle"]:
        print(f'{str(x["direccion"])[:23]:24s}{str(x["estado"]):13s}{str(x["amoblado"]):7s}'
              f'{str(x["mascotas"]):13s}{str(x["uso"]):11s}{str(x["dorm"]):5s}{str(x["desc_m2"]):>8s}')
