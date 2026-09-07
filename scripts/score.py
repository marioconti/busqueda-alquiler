"""Filtros duros y score de blandos.

Tres reglas por encima de la formula (seccion 5.b del prompt de arranque):

1. EL PRECIO NO ENTRA EN EL SCORE. Ya filtra como duro. Si ademas puntuara, lo barato subiria dos
   veces y el ranking terminaria mostrando lo peor de lo que entra en presupuesto.
2. estado = null puntua 20, no 65. El silencio del anunciante no es neutro.
3. Confianza visual baja -> score capeado en 70 y con asterisco.

Y una distincion propia que no estaba en el prompt pero hace falta:

   estado = null             -> el aviso NO dice nada       -> penaliza (20 puntos)
   estado = "sin_clasificar" -> NOSOTROS no lo leimos aun   -> el componente no se puntua,
                                                              el score queda PARCIAL y capeado

   Mezclar las dos cosas seria mentir en las dos direcciones: castigar a un aviso por un silencio
   que es nuestro, o darle 65 a algo que nunca leimos.

Uso directo:  python scripts/score.py        (recalcula y reescribe data/avisos.json)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import DIR_DATA, escribir_json, leer_json, load_config  # noqa: E402


# --------------------------------------------------------------------------- helpers

def _interpolar(valor: float, escala: list[float]) -> float:
    """Mapea `valor` sobre `escala` (n cortes) a 0..100 repartido en partes iguales."""
    if not escala:
        return 0.0
    n = len(escala)
    if n == 1:
        return 100.0 if valor >= escala[0] else 0.0
    paso = 100.0 / (n - 1)
    if valor <= escala[0]:
        return 0.0
    if valor >= escala[-1]:
        return 100.0
    for i in range(n - 1):
        lo, hi = escala[i], escala[i + 1]
        if lo <= valor <= hi:
            frac = 0.0 if hi == lo else (valor - lo) / (hi - lo)
            return paso * (i + frac)
    return 0.0


def _sin_acentos(txt) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(txt or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _mapear(valor, tabla: dict, por_defecto=None):
    if valor is None:
        return tabla.get("null", por_defecto)
    return tabla.get(str(valor), por_defecto)


def exterior_efectivo(aviso: dict, penal_techado: float):
    """m2 de exterior ponderados: lo techado vale la mitad.

    Devuelve (m2_efectivos, hay_dato, hay_faltante). `hay_faltante` marca que existe exterior
    declarado sin m2, o sea que el numero que devolvemos es un piso, no el valor real.

    ORDEN DE FUENTES:
      1. `m2_descubiertos` del PORTAL (m2 totales - m2 cubiertos de la ficha). Campo
         estructurado, no prosa. Ya excluye lo techado por definicion — un quincho cerrado
         computa como superficie cubierta — asi que no lleva penalizacion.
      2. La lista `exterior` leida del texto, con penalizacion a lo techado.
      3. `exterior_m2_total` suelto.

    Se prefiere (1) sobre (2) porque la prosa exagera: hay avisos que declaran 64 m2 de
    terraza sobre una superficie descubierta total de 40.
    """
    desc = aviso.get("m2_descubiertos")
    if desc is not None:
        return float(desc), True, False

    items = aviso.get("exterior") or []
    total, con_dato, sin_dato = 0.0, 0, 0
    for it in items:
        m2 = it.get("m2")
        if m2 is None:
            sin_dato += 1
            continue
        con_dato += 1
        total += float(m2) * (1.0 if it.get("descubierto", True) else penal_techado)
    if con_dato == 0 and sin_dato == 0:
        if aviso.get("exterior_m2_total") is not None:
            return float(aviso["exterior_m2_total"]), True, False
        return 0.0, False, False
    return total, con_dato > 0, sin_dato > 0


def categoria_expensas(aviso: dict):
    if aviso.get("expensas_cat"):
        return aviso["expensas_cat"]
    e = aviso.get("expensas_usd")
    if e is None:
        return None
    if e <= 0:
        return "sin_expensas"
    return "bajas" if e <= 100 else "altas"


TRANQUILIDAD_POR_TIPO = {"casa": "casa_lote_propio", "ph": "ph_entrada_indep", "departamento": "torre"}


# --------------------------------------------------------------------------- score

def calcular_score(aviso: dict, cfg: dict) -> dict:
    s = cfg["score"]
    reglas = cfg.get("reglas_score", {})
    comps: list[dict] = []

    def add(nombre, peso, puntos, detalle, inferido=False):
        comps.append({
            "componente": nombre, "peso": peso,
            "puntos": None if puntos is None else round(puntos, 1),
            "aporte": None if puntos is None else round(puntos * peso / 100.0, 2),
            "detalle": detalle, "inferido": inferido,
        })

    # 1. exterior (el que mas pesa)
    m2_ext, hay, faltante = exterior_efectivo(aviso, float(s["exterior_m2"].get("penalizacion_techado", 0.5)))
    if hay:
        p = _interpolar(m2_ext, s["exterior_m2"]["escala"])
        det = f"{m2_ext:.0f} m2 ponderados"
        if faltante:
            det += " (hay exterior declarado sin m2: es un piso, no el valor real)"
        add("exterior_m2", s["exterior_m2"]["peso"], p, det)
    else:
        n = len(aviso.get("exterior") or [])
        add("exterior_m2", s["exterior_m2"]["peso"], None,
            f"{n} espacio(s) exterior(es) declarado(s) sin m2" if n else "sin dato")

    # 2. m2 cubiertos
    if aviso.get("m2_cubiertos") is not None:
        p = _interpolar(float(aviso["m2_cubiertos"]), s["m2_cubiertos"]["escala"])
        add("m2_cubiertos", s["m2_cubiertos"]["peso"], p, f'{aviso["m2_cubiertos"]} m2')
    else:
        add("m2_cubiertos", s["m2_cubiertos"]["peso"], None, "sin dato")

    # 3. estado
    est = aviso.get("estado")
    if est == "sin_clasificar":
        add("estado", s["estado"]["peso"], None, "todavia no clasificado")
    else:
        p = _mapear(est, s["estado"]["valores"], 20)
        add("estado", s["estado"]["peso"], float(p),
            "el aviso no dice nada del estado (el silencio no es neutro)" if est is None else str(est))

    # 4. tranquilidad
    tr, inferido = aviso.get("tranquilidad"), False
    if tr is None and aviso.get("tipo"):
        tr = TRANQUILIDAD_POR_TIPO.get(aviso["tipo"])
        inferido = tr is not None
    if tr is None:
        add("tranquilidad", s["tranquilidad"]["peso"], None, "sin dato")
    else:
        p = float(_mapear(tr, s["tranquilidad"]["valores"], 50))
        det = tr + (" (inferido del tipo, sin verificar)" if inferido else "")
        if aviso.get("sobre_avenida"):
            p += float(s["tranquilidad"].get("penalizacion_avenida", 0))
            det += " · sobre avenida"
        if aviso.get("al_frente"):
            p += float(s["tranquilidad"].get("penalizacion_frente", 0))
            det += " · al frente"
        add("tranquilidad", s["tranquilidad"]["peso"], max(0.0, min(100.0, p)), det, inferido)

    # 5. banos. El toilette NO es un bano completo, pero tampoco es nada: Mario pidio
    # "idealmente dos banos, o bano y toillet". Cuenta como medio.
    b = aviso.get("banos_completos")
    if b is None:
        add("banos", s["banos"]["peso"], None, "sin dato")
    else:
        toi = min(int(aviso.get("toilettes") or 0), 2)
        efectivo = float(b) + 0.5 * toi
        p = _interpolar(efectivo, s["banos"]["escala"])
        add("banos", s["banos"]["peso"], p,
            f"{b} completo(s)" + (f" + {toi} toilette(s)" if toi else "") + f" = {efectivo:g}")

    # 5b. cochera
    coch = aviso.get("cochera")
    add("cochera", s.get("cochera", {}).get("peso", 0),
        None if coch is None else (100.0 if coch else 0.0),
        "sin dato" if coch is None else ("si" if coch else "no"))

    # 6. expensas
    ce = categoria_expensas(aviso)
    if ce is None:
        add("expensas", s["expensas"]["peso"], None, "sin dato")
    else:
        add("expensas", s["expensas"]["peso"], float(_mapear(ce, s["expensas"]["valores"], 10)), ce)

    # 7-8. bonus
    par = aviso.get("parrilla")
    add("parrilla_propia", s["parrilla_propia"], None if par is None else (100.0 if par == "propia" else 0.0),
        "sin dato" if par is None else str(par))
    # Edificio nuevo. Mario: "idealmente edificios nuevos". A estrenar puntua pleno y
    # baja hasta cero a los 30 anios; de ahi para arriba la antiguedad ya no discrimina.
    ant = aviso.get("antiguedad_anios")
    add("edificio_nuevo", s.get("edificio_nuevo", 0),
        None if ant is None else max(0.0, min(100.0, 100.0 - float(ant) * (100.0 / 30.0))),
        "sin dato" if ant is None else f"{round(float(ant))} anios")

    # Sin portero. No es capricho: el sueldo del encargado es el renglon mas grande de una
    # expensa, y Mario puso techo en USD 200. Un edificio sin portero es la forma mas
    # directa de que las expensas entren.
    port = aviso.get("portero")
    add("sin_portero", s.get("sin_portero", 0),
        None if port is None else (0.0 if port else 100.0),
        "sin dato" if port is None else ("tiene portero/encargado" if port else "sin portero"))

    ori = aviso.get("orientacion")
    add("orientacion_n_ne", s["orientacion_n_ne"],
        None if ori is None else (100.0 if str(ori).lower() in ("n", "ne", "norte", "noreste") else 0.0),
        "sin dato" if ori is None else str(ori))

    peso_disp = sum(c["peso"] for c in comps if c["puntos"] is not None)
    peso_total = sum(c["peso"] for c in comps)
    aporte = sum(c["aporte"] for c in comps if c["aporte"] is not None)

    # Un valor INFERIDO no es un valor medido, y hasta ahora la diferencia era invisible:
    # `tranquilidad` (peso 15, "prioritario" en el perfil) sale de una constante por tipo
    # cuando el aviso no dice nada, contaba como dato con dato, y por eso ni ensanchaba el
    # rango piso-techo ni bajaba la cobertura. Se reporta aparte para que se vea cuanta
    # parte del numero es medicion y cuanta es supuesto. NO cambia la cuenta: cambiarla
    # reordenaria el ranking entero y esa es una decision de Mario, no mia.
    peso_inferido = sum(c["peso"] for c in comps if c["puntos"] is not None and c.get("inferido"))

    parcial = peso_disp < peso_total

    # PISO: lo que la propiedad tiene DEMOSTRADO. Lo que falta suma 0.
    # TECHO: lo que daria si todo lo desconocido saliera tan bien como lo conocido.
    #
    # Por que un rango y no un numero: normalizar sobre lo conocido premia la falta de datos.
    # Un aviso sin exterior declarado se saltea el componente que mas pesa y sube; uno que
    # declara 40 m2 de terraza cobra 58 sobre 100 en ese componente y baja. Con el rango, el
    # unico modo de subir el piso es aportar datos. Se ordena por PISO.
    piso = aporte
    techo = 100.0 if peso_disp == 0 else aporte * 100.0 / peso_disp

    caps = []
    if parcial:
        caps.append(f"parcial: {peso_disp} de {peso_total} puntos de peso tienen dato")
    if aviso.get("confianza_visual") == "baja":
        cap = float(reglas.get("cap_confianza_visual_baja", 70))
        techo = min(techo, cap)
        caps.append(f"confianza visual baja (techo {cap:.0f})")

    return {
        "score": round(piso, 1),
        "score_piso": round(piso, 1),
        "score_techo": round(max(techo, piso), 1),
        "parcial": parcial,
        "cobertura": round(100.0 * peso_disp / peso_total, 0) if peso_total else 0,
        "peso_con_dato": peso_disp,
        "peso_inferido": peso_inferido,
        "peso_total": peso_total,
        "caps": caps,
        "componentes": comps,
    }


# --------------------------------------------------------------------------- duros

def evaluar_duros(aviso: dict, cfg: dict) -> dict:
    d = cfg["duros"]
    al = cfg["al_limite"]
    fallos, indeterminados = [], []

    def chequear(nombre, ok, desvio=None, detalle=""):
        if ok is None:
            indeterminados.append({"filtro": nombre, "detalle": detalle})
        elif not ok:
            fallos.append({"filtro": nombre, "desvio": desvio, "detalle": detalle})

    precio = aviso.get("precio_total_usd")
    tope = float(d["presupuesto_usd_max"])
    chequear("presupuesto", None if precio is None else precio <= tope,
             None if precio is None else (precio - tope) / tope,
             f"USD {precio} vs tope {tope:.0f}" if precio is not None else "sin precio")

    # Expensas: solo filtra a los que las DECLARAN. El que no las publica queda
    # indeterminado (pasa, pero marcado), porque 8 de cada 10 avisos no las dicen y
    # sacarlos a todos seria perder el inventario por un dato que no depende de nosotros.
    # Un departamento sin terraza de verdad no entra, por mas que cumpla todo lo demas.
    # Estaba escrito en el perfil desde el dia uno ("un balcon no alcanza") y NO estaba
    # codificado: por eso la primera corrida de departamentos devolvio 16 candidatos con
    # exteriores de 2, 3 y 6 m2. La regla mira el dato ESTRUCTURADO del portal
    # (m2 totales - m2 cubiertos), no la prosa, que exagera.
    tp = cfg.get("tipos", {})
    if aviso.get("tipo") == "departamento" and tp.get("departamento_requiere_terraza_propia_declarada"):
        minimo = float(tp.get("departamento_exterior_min_m2", 15))
        ext, hay, _ = exterior_efectivo(aviso, 0.5)
        chequear("terraza_depto", (ext >= minimo) if hay else None,
                 ((minimo - ext) / minimo) if hay else None,
                 f"{ext:.0f} m2 de exterior vs minimo {minimo:.0f} para departamento" if hay
                 else "no declara superficie descubierta")

    tope_exp = d.get("expensas_usd_max")
    if tope_exp:
        exp = aviso.get("expensas_usd")
        chequear("expensas", None if exp is None else exp <= float(tope_exp),
                 None if exp is None else (exp - float(tope_exp)) / float(tope_exp),
                 f"USD {round(exp)} vs tope {float(tope_exp):.0f}" if exp is not None
                 else "el aviso no declara expensas")

    dorm, mind = aviso.get("dormitorios_reales"), float(d["dormitorios_reales_min"])
    chequear("dormitorios", None if dorm is None else dorm >= mind,
             None if dorm is None else (mind - dorm) / mind,
             f"{dorm} reales vs minimo {mind:.0f}" if dorm is not None else "sin dato")

    amb, mina = aviso.get("ambientes_declarados"), float(d.get("ambientes_min") or 0)
    if mina:
        chequear("ambientes", None if amb is None else amb >= mina,
                 None if amb is None else (mina - amb) / mina,
                 f"{amb} amb vs minimo {mina:.0f}" if amb is not None else "sin dato")

    # BANOS. Mario 2026-09-07: "no quiero departamento de dos ambientes, con un solo
    # bano ni casas". El dato NO vive en `banos` —ese campo esta vacio en el 100% de los
    # avisos— sino en `banos_completos` + `toilettes`, y un toilette cuenta medio, que es
    # como el perfil lo viene diciendo desde el principio ("dos banos, o bano y toilette").
    # Leerlo del campo equivocado dejaba la lista corta en cero sin un solo error.
    bmin = float(d.get("banos_min") or 0)
    if bmin:
        bc = aviso.get("banos_completos")
        tl = aviso.get("toilettes") or 0
        tot = None if bc is None else bc + 0.5 * tl
        chequear("banos", None if tot is None else tot >= bmin,
                 None if tot is None else (bmin - tot) / bmin,
                 f"{bc} banos + {tl} toilette vs minimo {bmin:g}" if tot is not None else "sin dato")

    # TIPO. Mismo pedido: "casas no, Juan no quiere irse a casas". Es un binario, no
    # admite tolerancia: una casa no es una casa por poco.
    permitidos = d.get("tipos_permitidos")
    if permitidos:
        tp = (aviso.get("tipo") or "").lower()
        chequear("tipo", None if not tp else tp in permitidos, None, tp or "sin dato")

    m2, minm = aviso.get("m2_cubiertos"), float(d["m2_cubiertos_min"])
    chequear("m2_cubiertos", None if m2 is None else m2 >= minm,
             None if m2 is None else (minm - m2) / minm,
             f"{m2} m2 vs minimo {minm:.0f}" if m2 is not None else "sin dato")

    amo = aviso.get("amoblado")
    chequear("amoblado", None if amo is None else not amo, None,
             "amoblado" if amo else ("sin dato" if amo is None else "sin amoblar"))

    mas = aviso.get("mascotas")
    if mas is None or mas == "a_confirmar":
        indeterminados.append({"filtro": "mascotas", "detalle": "a confirmar (se muestra igual, marcado)"})
    else:
        chequear("mascotas", mas in ("si", "solo_gato"), None, str(mas))

    uso = aviso.get("uso_permitido")
    chequear("uso", None if uso is None else uso in d["usos_permitidos"], None, uso or "sin dato")

    # Zona excluida. Se mira el campo barrio Y el texto: Las Canitas se publica como
    # Belgrano y como Palermo, asi que por barrio solo no se atrapa.
    zonas = cfg.get("zonas", {})
    barrio = _sin_acentos(aviso.get("barrio"))
    texto = _sin_acentos(" ".join(str(aviso.get(c) or "") for c in ("titulo", "descripcion", "direccion")))
    excluida = next((z for z in (zonas.get("excluidas") or [])
                     if _sin_acentos(z) and _sin_acentos(z) in barrio), None)
    if not excluida:
        excluida = next((t for t in (zonas.get("excluidas_por_texto") or [])
                         if _sin_acentos(t) in texto), None)

    # Y ademas tiene que ESTAR en las zonas incluidas. Sin esto, un aviso de un barrio que
    # nadie pidio pasaba como candidato: alcanzaba con que no estuviera en la lista negra.
    # Paso de verdad cuando un bug del config disparo una busqueda de toda CABA.
    incluidas = [_sin_acentos(z) for z in (zonas.get("incluidas") or [])]
    fuera = bool(barrio) and incluidas and not any(z in barrio for z in incluidas)

    if fuera and not excluida:
        excluida = f"{aviso.get('barrio')} no esta en las zonas buscadas"
    chequear("zona", excluida is None, None, f"zona: {excluida}" if excluida else "ok")

    est = aviso.get("estado")
    if est in (None, "sin_clasificar"):
        indeterminados.append({"filtro": "estado", "detalle": "sin clasificar" if est == "sin_clasificar" else "el aviso no lo declara"})
    else:
        chequear("estado", est not in d["estados_rechazados"], None, str(est))

    binarios = set(al.get("filtros_sin_tolerancia") or [])
    tol = float(al.get("tolerancia", 0.15))
    al_limite = (
        len(fallos) <= int(al.get("max_duros_fallados", 1))
        and len(fallos) > 0
        and all(f["filtro"] not in binarios and f["desvio"] is not None and abs(f["desvio"]) < tol for f in fallos)
    )
    return {
        "pasa": len(fallos) == 0,
        "fallos": fallos,
        "indeterminados": indeterminados,
        "al_limite": al_limite,
        "al_limite_por": [f["filtro"] for f in fallos] if al_limite else [],
    }


ORDEN_ESTADO = {"a_estrenar": 5, "reciclado": 4, "bueno": 3, "sin_clasificar": 2, None: 1, "cosmetico": 0, "a_refaccionar": -1}


def clave_orden_default(aviso: dict):
    """Seccion 8: primero ESTADO VISUAL, despues score de blandos.

    Una propiedad deteriorada con 100 m2 de terraza no va arriba.

    Ojo con la palabra "visual": el desempate es por `estado_visual`, que sale de mirar
    las FOTOS, no por el `estado` que sale de leer el texto. Usar el de texto ordenaba
    mal: dejaba arriba avisos de score bajo solo porque el anunciante uso la palabra
    "reciclado", y hundia a Conde 4700 (63 de piso) por debajo de Plaza 2474 (40) porque
    uno se quedo callado sobre el estado y el otro no.

    Mientras no haya pasada de fotos, todos empatan en el primer criterio y manda el score.
    """
    est = aviso.get("estado_visual")
    return (-ORDEN_ESTADO.get(est, 1) if est else 0, -(aviso.get("score") or 0))


def procesar(avisos: list[dict], cfg: dict) -> list[dict]:
    for a in avisos:
        res = calcular_score(a, cfg)
        a["score"] = res["score"]
        a["score_desglose"] = res
        duros = evaluar_duros(a, cfg)
        a["duros"] = duros
        if a.get("pinned"):
            a["seccion"] = "favoritos"
        elif duros["pasa"]:
            a["seccion"] = "candidatos"
        elif duros["al_limite"]:
            a["seccion"] = "al_limite"
        else:
            a["seccion"] = "filtrados"
        if duros["al_limite"] and not a.get("al_limite_por"):
            a["al_limite_por"] = duros["al_limite_por"]
    return avisos


if __name__ == "__main__":
    cfg = load_config()
    doc = leer_json(DIR_DATA / "avisos.json")
    procesar(doc["avisos"], cfg)
    escribir_json(DIR_DATA / "avisos.json", doc)
    print(f'{"piso":>5} {"techo":>6} {"cob":>4}  {"seccion":11s}  direccion')
    for a in sorted(doc["avisos"], key=clave_orden_default):
        d = a["score_desglose"]
        print(f'{d["score_piso"]:5.1f} {d["score_techo"]:6.1f} {d["cobertura"]:3.0f}%  '
              f'{a["seccion"]:11s}  {a["direccion"]:24s}  {a["barrio"]}')
