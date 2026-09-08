"""Corrida diaria. Los diez pasos de la seccion 11, en orden.

  1. Leer pendiente.json y aplicar las decisiones anteriores.
  2. Bajar y parsear todo, sin filtro de fecha, en todos los portales.
  3. Deduplicar y fusionar, dentro y entre portales.
  4. Clasificar con la API SOLO lo que no este clasificado.
  5. Aplicar duros, puntuar blandos, armar "Al limite".
  6. Filtrar contra descartados.json.
  7. Detectar desapariciones y cambios de precio.
  8. Regenerar la pagina.
  9. Escribir el log en corridas/.
 10. Contar en el chat solo lo nuevo, en tres lineas.

Uso:
    python scripts/main.py                # corrida completa
    python scripts/main.py --sin-red      # todo menos bajar y clasificar
    python scripts/main.py --sin-api      # baja y parsea, no gasta API
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import (DIR_CORRIDAS, DIR_DATA, DIR_WEB, escribir_json,  # noqa: E402
                        leer_json, load_config, normalizar_direccion, zonas_a_barrer)

HOY = date.today().isoformat()


# --------------------------------------------------- 1. decisiones pendientes

TIPO_POR_ACCION = {"descartar": "descarte", "interesa": "favorito",
                   "vista_online": "vista_online"}


def aplicar_pendientes() -> list[str]:
    """Ingesta del pendiente.json que exporta la pagina en modo file://.

    Con el servidor local (abrir.bat) esto no hace falta: la pagina escribe directo en
    la bitacora. Esta ruta queda para cuando la pagina se abre con doble click.

    Lo importante: NO aplica las decisiones a mano, las convierte en eventos y deja que
    el replay haga el resto. Un solo camino de escritura, un solo lugar donde mirar.
    """
    import eventos

    ruta = DIR_WEB / "pendiente.json"
    if not ruta.exists():
        return []
    payload = leer_json(ruta, {})
    decisiones = payload.get("decisiones", [])
    lineas = []

    for d in decisiones:
        tipo = TIPO_POR_ACCION.get(d.get("accion"))
        if not tipo:
            continue
        eventos.registrar(tipo, d.get("id"), origen="web-export",
                          direccion=d.get("direccion"), barrio=d.get("barrio"),
                          precio_usd=d.get("precio_usd"),
                          motivo=d.get("motivo_literal") or None, url=d.get("url"))
        lineas.append(f'{tipo} {d.get("direccion")}' +
                      (f': "{d.get("motivo_literal")}"' if d.get("motivo_literal") else ""))

    if decisiones:
        eventos.sincronizar()
    if payload.get("cotizacion_bna_venta"):
        doc_av = leer_json(DIR_DATA / "avisos.json")
        doc_av.setdefault("meta", {})["cotizacion_bna_venta"] = payload["cotizacion_bna_venta"]
        escribir_json(DIR_DATA / "avisos.json", doc_av)
    ruta.unlink()
    return lineas


# --------------------------------------------------- 6. veto por descartados

def indice_descartes() -> dict[str, dict]:
    doc = leer_json(DIR_DATA / "descartados.json", {"descartados": []})
    return {d["direccion_norm"]: d for d in doc["descartados"] if d.get("direccion_norm")}


def esta_vetado(aviso: dict, descartes: dict, cfg: dict) -> tuple[bool, str | None]:
    """Un descartado vuelve a mostrarse si bajo el precio mas del umbral, o si el aviso
    se edito y ahora resuelve el motivo. En ese caso se muestra CON un cartel."""
    d = descartes.get(aviso.get("direccion_norm"))
    if not d:
        return False, None
    antes, ahora = d.get("precio_usd"), aviso.get("precio_total_usd")
    umbral = float(cfg["reglas_reaparicion"]["baja_precio_min_pct"])
    if antes and ahora and (antes - ahora) / antes > umbral:
        return False, f'REAPARECE: bajo de USD {antes:,.0f} a USD {ahora:,.0f}'.replace(",", ".")
    return True, None


# --------------------------------------------------- 7. desapariciones y precios

def reconciliar(previos: list[dict], nuevos: list[dict], cfg: dict,
                vistos: set[str] | None = None) -> dict:
    """`vistos` son los ids que YA pasaron por la base alguna vez, aunque hoy no esten.

    POR QUE HACE FALTA. Dos cosas sacan avisos de `avisos.json` despues de entrar: la
    deduplicacion (fusiona el duplicado y lo borra) y el veto por descarte. Pero el HTML
    los sigue trayendo en cada barrido, asi que sin este registro vuelven a contar como
    ALTA todos los dias: el 2026-08-21 tres corridas seguidas reportaron ~182 "avisos
    nuevos" con la base clavada en 1.916. **El numero que decide si vale la pena mirar
    era el mas mentiroso del sistema.**
    """
    # DOS CONJUNTOS DISTINTOS, Y MEZCLARLOS ROMPIO EL CONTADOR OTRA VEZ (2026-08-23).
    #   historicos = ids que pasaron por la base ALGUNA VEZ  -> decide que es un ALTA
    #   presentes  = ids que trajo el barrido de HOY         -> decide quien esta ausente
    # Se llamaban los dos `vistos`, y el desempaquetado de la linea de abajo pisaba el
    # parametro con un set vacio. Como el id se agregaba tres lineas antes de preguntar
    # si estaba, la condicion daba siempre False y `altas` volvia SIEMPRE vacia: la
    # corrida del 2026-08-23 entro 89 avisos de MercadoLibre e informo "hoy no hay nada".
    # Es el mismo contador que el 2026-08-21 mentia al reves (182 altas todos los dias).
    # Si vuelve a tocarse: son dos conjuntos, nunca uno.
    historicos = set(vistos or ())
    por_id = {a["id"]: a for a in previos}
    presentes, cambios, desaparecidos, altas, ausentes = set(), [], [], [], []

    for n in nuevos:
        presentes.add(n["id"])
        viejo = por_id.get(n["id"])
        if viejo is None:
            n["first_seen"] = HOY
            n["last_seen"] = HOY
            n["estado_aviso"] = "vigente"
            n["historial_precio"] = ([{"fecha": HOY, "precio_total_usd": n.get("precio_total_usd")}]
                                     if n.get("precio_total_usd") else [])
            por_id[n["id"]] = n
            if n["id"] not in historicos:
                altas.append(n)
            continue
        antes = viejo.get("precio_total_usd")
        ahora = n.get("precio_total_usd")
        if ahora is not None and antes is not None and ahora != antes:
            viejo.setdefault("historial_precio", []).append({"fecha": HOY, "precio_total_usd": ahora})
            cambios.append({"id": viejo["id"], "direccion": viejo.get("direccion"),
                            "antes": antes, "ahora": ahora,
                            "pct": round((ahora - antes) / antes * 100, 1)})
        for k, v in n.items():
            if v not in (None, [], "", {}) and k not in ("historial_precio", "first_seen"):
                viejo[k] = v
        viejo["last_seen"] = HOY
        viejo["estado_aviso"] = "vigente"

    for a in por_id.values():
        # NO SALIR EN UN BARRIDO NO ES CAERSE, Y CONFUNDIRLO COSTO CARO.
        # El 2026-08-15 este bucle marco 300 avisos como desaparecidos en un solo dia
        # -el 26% de la base- y una verificacion contra el portal mostro que 7 de cada 8
        # seguian publicados. El barrido baja hasta max_paginas_por_barrio ordenado por
        # precio: todo lo que queda debajo del corte -o lo que se corre de pagina porque
        # ese dia entraron avisos nuevos mas baratos- desaparece del listado sin haberse
        # caido. El comentario viejo prometia mirar si el barrio se habia barrido; nunca
        # se implemento, y aun implementado no alcanzaria: el corte es por pagina, no por
        # barrio.
        #
        # La unica evidencia valida de una caida es pedir la URL y que el portal conteste
        # 404/410 o la pagina de "aviso no disponible". Eso lo hace detalle.py, y es el
        # unico que escribe estado_aviso = "desaparecido".
        #
        # Aca solo se cuenta la ausencia: sirve para priorizar a quien revalidar primero.
        if a["id"] in presentes or a.get("estado_aviso") == "desaparecido":
            a["ausente_veces"] = 0
            continue
        if a.get("fuente_datos") == "semilla" and a.get("last_seen") == a.get("first_seen"):
            continue  # nunca se verifico contra el portal; no hay de que caerse
        if not nuevos:
            continue  # --sin-red / --desde-cache: no hubo barrido, nadie estuvo ausente
        a["ausente_veces"] = int(a.get("ausente_veces") or 0) + 1
        ausentes.append(a)

    return {"avisos": list(por_id.values()), "altas": altas, "ausentes": ausentes,
            "cambios_precio": cambios, "desaparecidos": desaparecidos}


# --------------------------------------------------- orquestacion

def correr(sin_red: bool = False, sin_api: bool = False, desde_cache: bool = False,
           solo_zonas: list | None = None) -> dict:
    cfg = load_config()
    log: dict = {"fecha": HOY, "pendientes": [], "bajados": 0, "parseados": 0,
                 "altas": [], "cambios_precio": [], "desaparecidos": [], "avisos_vetados": 0}

    log["pendientes"] = aplicar_pendientes()

    nuevos: list[dict] = []
    if desde_cache:
        # Reprocesar todo lo que ya esta bajado, SIN tocar la red. Es lo que hace falta
        # despues de un 403, o cuando cambia el parser y hay que releer lo de hoy.
        import fetch
        import parse
        dias = sorted(p for p in fetch.DIR_CRUDO.glob("*") if p.is_dir())
        if dias:
            bajados = {p.stem.replace("__", "/"): str(p) for p in dias[-1].glob("*.html")}
            log["bajados"] = len(bajados)
            nuevos = parse.parsear_todo(bajados)
            log["parseados"] = len(nuevos)
            print(f"  desde cache: {len(bajados)} paginas -> {len(nuevos)} avisos unicos")
    elif not sin_red:
        import fetch
        import parse

        # TECHO DE BARRIDOS POR DIA. Antes lo unico que lo sostenia era que las corridas
        # las lanzaba Mario a mano; desde que hay una tarea programada, la de la manana y
        # una manual se suman sin que nadie lleve la cuenta. El portal ya contesto 403 dos
        # veces, y la etiqueta del proyecto (dos corridas por dia, pausa, sin evadir nada)
        # no se sostiene con la memoria de nadie: se sostiene con esto.
        doc_prev = leer_json(DIR_DATA / "avisos.json")
        hechos = int((doc_prev.get("meta", {}).get("barridos_por_dia", {}) or {}).get(HOY, 0))
        tope_dia = int(cfg.get("rate_limit", {}).get("corridas_por_dia_max", 2))
        # `--solo-zonas` NO es un rodeo del tope: el tope existe para no volver a pedir
        # LO MISMO muchas veces al dia (dos 403 de Zonaprop lo pusieron ahi). Cuando se
        # suma una zona al config, esa geografia no se pidio NUNCA, y esperar al dia
        # siguiente no protege a nadie. Va acotado a la lista que se nombra, es manual,
        # y suma al contador igual.
        if hechos >= tope_dia and solo_zonas:
            print(f"  ·  tope diario alcanzado, pero se pidieron zonas nuevas: "
                  f"{', '.join(solo_zonas)}")
        if hechos >= tope_dia and not solo_zonas:
            print(f"  !  ya se barrio {hechos} vez/veces hoy (tope {tope_dia}). "
                  f"Se saltea la red y se reprocesa lo que hay.")
            log["barrido_salteado"] = True
            # Salteado no es vacio: lo que ya se bajo hoy se reprocesa igual, gratis.
            hoy_dir = fetch.DIR_CRUDO / HOY
            bajados = ({p.stem.replace("__", "/"): str(p) for p in hoy_dir.glob("*.html")}
                       if hoy_dir.exists() else {})
        else:
            bajados = fetch.correr(solo_zonas) if solo_zonas else fetch.correr()
            doc_prev.setdefault("meta", {}).setdefault("barridos_por_dia", {})[HOY] = hechos + 1
            escribir_json(DIR_DATA / "avisos.json", doc_prev)

        # TODO lo bajado hoy se parsea, no solo lo que trajo ESTA corrida. Si el
        # presupuesto de pedidos corto la corrida anterior a mitad de camino, o si la
        # rotacion de barrios hizo que hoy no se pidieran las mismas paginas, esos HTML
        # ya estan en disco y parsearlos es gratis. La segunda corrida del 2026-08-21
        # dejo 181 avisos sin procesar por esto.
        hoy_dir = fetch.DIR_CRUDO / HOY
        if hoy_dir.exists():
            for f in hoy_dir.glob("*.html"):
                bajados.setdefault(f.stem.replace("__", "/"), str(f))

        log["bajados"] = len(bajados)
        nuevos = parse.parsear_todo(bajados) if bajados else []
        log["parseados"] = len(nuevos)

        # Segundo portal. Va DESPUES de Zonaprop y sus avisos entran al mismo pozo: la
        # deduplicacion de mas abajo corre sobre todo el inventario y la clave
        # (calle, altura, m2/10) no mira el portal, asi que el mismo inmueble publicado
        # en los dos se fusiona solo. Si Argenprop falla, la corrida sigue: es inventario
        # extra, no la fuente principal.
        ap_cfg = (cfg.get("portales") or {}).get("argenprop") or {}
        if ap_cfg.get("activo") and not log.get("barrido_salteado"):
            try:
                import argenprop
                extra = argenprop.buscar(solo_zonas or zonas_a_barrer(cfg),
                                         int(ap_cfg.get("paginas", 2)), cfg)
                log["argenprop"] = len(extra)
                nuevos.extend(extra)
                print(f"  argenprop: {len(extra)} avisos")
            except Exception as e:  # noqa: BLE001
                log["argenprop_error"] = str(e)
                print(f"  !  argenprop fallo, se sigue con Zonaprop: {e}")

        # Tercer portal, mismo criterio que el segundo: entra al mismo pozo y la
        # deduplicacion por (calle, altura, m2/10) lo fusiona con lo que ya este.
        # Sus barrios son PROPIOS (portales.mercadolibre_zonas): Mario lo quiere solo
        # en el corredor norte, no en toda la busqueda. Y no acepta paginas: robots.txt
        # prohibe `_Desde_`, asi que el tope es en pedidos, no en paginas.
        #
        # CONTADOR PROPIO, y no es un rodeo del tope. El tope de arriba cuenta los
        # barridos de ZONAPROP: nacio de los dos 403 de ese portal y protege ese
        # presupuesto de pedidos. Colgar a MercadoLibre de ese mismo contador mezcla
        # dos cosas distintas — con Zonaprop agotado, ML no se pediria ni una vez en
        # todo el dia aunque no se lo hubiera tocado. La etiqueta es POR SITIO: cada
        # portal lleva su cuenta y respeta el mismo maximo.
        ml_cfg = (cfg.get("portales") or {}).get("mercadolibre") or {}
        if ml_cfg.get("activo"):
            doc_ml = leer_json(DIR_DATA / "avisos.json")
            hechos_ml = int((doc_ml.get("meta", {}).get("barridos_ml_por_dia", {})
                             or {}).get(HOY, 0))
            if hechos_ml >= tope_dia and not solo_zonas:
                print(f"  !  mercadolibre ya se barrio {hechos_ml} vez/veces hoy "
                      f"(tope {tope_dia}): se saltea")
                log["mercadolibre_salteado"] = True
            else:
                try:
                    import mercadolibre
                    zonas_ml = ([z for z in solo_zonas] if solo_zonas
                                else mercadolibre.zonas_de(cfg))
                    extra = mercadolibre.buscar(zonas_ml, cfg,
                                                int(ml_cfg.get("max_requests", 21)))
                    log["mercadolibre"] = len(extra)
                    nuevos.extend(extra)
                    print(f"  mercadolibre: {len(extra)} avisos")
                    # Se cuenta el barrido aunque haya vuelto vacio: el costo en
                    # pedidos ya se pago, que es lo que el tope protege.
                    doc_ml.setdefault("meta", {}).setdefault(
                        "barridos_ml_por_dia", {})[HOY] = hechos_ml + 1
                    escribir_json(DIR_DATA / "avisos.json", doc_ml)
                except Exception as e:  # noqa: BLE001
                    log["mercadolibre_error"] = str(e)
                    print(f"  !  mercadolibre fallo, se sigue: {e}")

    doc = leer_json(DIR_DATA / "avisos.json")
    previos = doc["avisos"]

    # CUANDO SE TOCO LA RED POR ULTIMA VEZ. Es el dato que faltaba el 2026-08-21: el
    # sistema llevaba seis dias sin bajar nada y en la pantalla no habia forma de notarlo
    # -"generado" se actualiza con cualquier rebuild, aunque no haya habido barrido-. Un
    # sistema congelado que no avisa que esta congelado se lee como un mercado sin
    # movimiento, que es la peor conclusion posible.
    if nuevos and not sin_red and not desde_cache:
        doc.setdefault("meta", {})["ultimo_barrido"] = HOY

    # Guardia contra el parser roto en silencio: si antes habia inventario y hoy el
    # parseo devuelve cero, es mucho mas probable que se haya roto el parser a que el
    # mercado se haya vaciado. Se aborta antes de marcar todo como desaparecido.
    if not sin_red and not log.get("barrido_salteado") and previos and not nuevos:
        raise SystemExit("ABORTA: el parseo devolvio 0 avisos y la base no esta vacia. "
                         "Revisar parse.py contra el HTML de data/raw/ antes de seguir.")

    doc_vistos = leer_json(DIR_DATA / "ids_vistos.json", {"ids": []})
    vistos = set(doc_vistos.get("ids", []))
    rec = reconciliar(previos, nuevos, cfg, vistos)
    doc["avisos"] = rec["avisos"]

    # Deduplicacion sobre TODO el inventario, no solo sobre lo recien bajado: un aviso
    # nuevo puede ser el mismo inmueble que uno que ya estaba en la base.
    import parse as _parse
    antes_dedup = len(doc["avisos"])
    doc["avisos"] = _parse.deduplicar(doc["avisos"])
    log["fusionados"] = antes_dedup - len(doc["avisos"])
    log["altas"] = [{"id": a["id"], "direccion": a.get("direccion")} for a in rec["altas"]]
    log["cambios_precio"] = rec["cambios_precio"]
    log["desaparecidos"] = [{"id": a["id"], "direccion": a.get("direccion"),
                             "era_favorito": bool(a.get("pinned"))} for a in rec["desaparecidos"]]
    # Ausente no es caido: es "no salio en el barrido de hoy". Se informa aparte y con
    # otro nombre justamente para que no se lea como una caida.
    log["ausentes"] = len(rec.get("ausentes", []))

    descartes = indice_descartes()
    for a in doc["avisos"]:
        vetado, cartel = esta_vetado(a, descartes, cfg)
        a["vetado"] = vetado
        a["cartel_reaparicion"] = cartel
        if vetado:
            log["avisos_vetados"] += 1
    doc["avisos"] = [a for a in doc["avisos"] if not a["vetado"]]

    escribir_json(DIR_DATA / "avisos.json", doc)

    # El registro de ids vistos se guarda DESPUES de deduplicar y vetar, y con todo lo
    # que se parseo hoy: justamente los que la dedup y el veto acaban de sacar de la base
    # son los que no tienen que volver a contarse como novedad mañana.
    vistos |= {a["id"] for a in nuevos if a.get("id")}
    vistos |= {a["id"] for a in doc["avisos"] if a.get("id")}
    escribir_json(DIR_DATA / "ids_vistos.json", {"ids": sorted(vistos)})

    # --- ficha de detalle + fotos locales.
    #
    # Desde que se descubrio que el LISTADO ya trae descripcion, fotos, expensas y
    # antiguedad, abrir la ficha dejo de ser necesario para el grueso. Cuesta 1 request
    # + 6 de imagenes por aviso: con 300 avisos serian 2100 requests para conseguir casi
    # nada nuevo. Entonces se reserva para dos cosas:
    #
    #   1. LOS FAVORITOS, siempre. Es la revalidacion diaria: saber si siguen publicados.
    #      Un favorito que se cae y no se avisa es el peor fallo del sistema.
    #   2. Los mejores N que todavia no tengan ficha, para tener sus fotos en local.
    if not sin_red:
        import detalle
        import score as _score

        _score.procesar(doc["avisos"], cfg)
        objetivo = [a["id"] for a in doc["avisos"] if a.get("pinned")]

        # REVALIDAR VIGENCIA ES BARATO Y BAJAR LA FICHA NO. Estaban en el mismo
        # presupuesto, y por eso habia 305 avisos en cola de revalidacion con un tope
        # de 15 por corrida: la cola crecia veinte veces mas rapido de lo que se
        # vaciaba. Resultado medido el 2026-09-08: 129 avisos llevaban 18 barridos sin
        # aparecer y seguian listados como vigentes, y el 42% de la lista corta no
        # habia salido en el barrido del dia. Mario, en sus palabras: "siento que
        # siempre veo lo mismo". Lo estaba viendo: inventario muerto sostenido arriba
        # por su score.
        #
        # `solo_vigencia` ya existia en detalle.py y nadie lo llamaba: es UN pedido,
        # sin fotos y sin reparsear la ficha. Con eso la revalidacion tiene su propia
        # cuota, mucho mas alta, sin tocar el presupuesto de fichas.
        vig = int(cfg.get("fotos", {}).get("vigencia_por_corrida", 60))
        if vig > 0:
            sospechosos = [a for a in doc["avisos"]
                           if a.get("seccion") in ("candidatos", "al_limite", "favoritos")
                           and a.get("estado_aviso") != "desaparecido"
                           and (a.get("ausente_veces") or 0) >= 2]
            # El que lleva mas barridos sin aparecer es del que menos se sabe.
            sospechosos.sort(key=lambda a: -(a.get("ausente_veces") or 0))
            if sospechosos:
                rv = detalle.refrescar([a["id"] for a in sospechosos[:vig]], solo_vigencia=True)
                log["vigencia_revisada"] = len(rv["ok"]) + len(rv["desaparecidos"])
                log["vigencia_pendiente"] = max(0, len(sospechosos) - vig)
                log["desaparecidos"] += [d for d in rv["desaparecidos"]
                                         if d["id"] not in {x["id"] for x in log["desaparecidos"]}]
                # El barrido de vigencia acaba de cambiar estado_aviso: sin volver a
                # puntuar, los que se cayeron siguen en la lista corta de esta corrida.
                _score.procesar(doc["avisos"], cfg)

        tope = int(cfg.get("fotos", {}).get("fichas_por_corrida", 15))
        if tope > 0:
            # Primero los candidatos que hoy no salieron en el barrido: son los unicos de
            # los que hay una duda concreta de vigencia, y pedir su URL es lo unico que la
            # resuelve. Despues, los que todavia no tienen ficha, por score.
            candidatos = [a for a in doc["avisos"]
                          if not a.get("pinned") and a.get("seccion") in ("candidatos", "al_limite")]
            dudosos = [a for a in candidatos if a.get("ausente_veces")]
            dudosos.sort(key=lambda a: (-(a.get("ausente_veces") or 0), -(a.get("score") or 0)))
            frescos = [a for a in candidatos
                       if not a.get("ficha_leida_el") and not a.get("ausente_veces")]
            frescos.sort(key=lambda a: -(a.get("score") or 0))
            cola = dudosos + frescos
            objetivo += [a["id"] for a in cola[:tope]]
            log["fichas_pendientes"] = max(0, len(cola) - tope)
            log["revalidacion_pendiente"] = max(0, len(dudosos) - tope)

        if objetivo:
            r = detalle.refrescar(objetivo)
            log["fichas"] = len(r["ok"])
            log["fotos_bajadas"] = r["fotos"]
            log["desaparecidos"] += [d for d in r["desaparecidos"]
                                     if d["id"] not in {x["id"] for x in log["desaparecidos"]}]
            log["cambios_ficha"] = r["cambios"]

        import cotizacion
        log["cotizacion"] = cotizacion.aplicar()["cotizacion"]

    # --- reglas (gratis) antes que la API (cuesta): lo que resuelve el vocabulario no
    # se manda a clasificar.
    import reglas
    log["reglas"] = reglas.aplicar()["clasificados"]

    # Mirar fotos ya NO pasa por la API: lo hace Claude en la sesion, sin creditos. La
    # corrida deja el lote armado y avisa cuantos esperan; el paso manual es
    # `clasificar.py aplicar` despues de mirarlas.
    if not sin_api:
        import clasificar
        try:
            pend = clasificar.pendientes(12)
            log["pendientes_clasificar"] = len(pend["items"])
        except Exception as e:  # noqa: BLE001
            log["pendientes_clasificar_error"] = str(e)

    import eventos
    eventos.sincronizar()

    import build
    log["resumen"] = build.build()
    escribir_log(log)
    return log


# --------------------------------------------------- 9. log de la corrida

def escribir_log(log: dict) -> Path:
    """ANEXA al log del dia. Nunca sobreescribe.

    La primera version reescribia el archivo entero y se llevo puesto un log del dia
    redactado a mano. El log de la corrida es un apendice del dia, no el dia entero.
    """
    from datetime import datetime as _dt

    r = log.get("resumen", {})
    lineas = [
        f'## Corrida automatica {_dt.now().strftime("%H:%M")}', "",
        f'- Listados bajados: {log["bajados"]}',
        f'- Avisos parseados (unicos, ya deduplicados): {log["parseados"]}',
        f'- Altas: {len(log["altas"])}',
        f'- Cambios de precio: {len(log["cambios_precio"])}',
        f'- Desapariciones: {len(log["desaparecidos"])}',
        f'- Vetados por descartes previos: {log["avisos_vetados"]}',
        f'- En base tras la corrida: {r.get("total_avisos", "?")} -> {r.get("por_seccion", {})}',
        "",
    ]
    if log["pendientes"]:
        lineas += ["### Decisiones aplicadas", ""] + [f"- {t}" for t in log["pendientes"]] + [""]
    if log.get("cambios_ficha"):
        lineas += ["### La ficha corrigio la base", ""]
        lineas += [f'- {c["direccion"]}: {c["campo"]} {c["antes"]} -> {c["ahora"]}'
                   for c in log["cambios_ficha"]] + [""]
    if log["cambios_precio"]:
        lineas += ["### Cambios de precio", ""]
        lineas += [f'- {c["direccion"]}: USD {c["antes"]} -> {c["ahora"]} ({c["pct"]:+.1f}%)'
                   for c in log["cambios_precio"]] + [""]
    if log["desaparecidos"]:
        lineas += ["### Desapariciones", ""]
        lineas += [f'- {d["direccion"]}' + ("  **ERA FAVORITO — AVISAR HOY**" if d["era_favorito"] else "")
                   for d in log["desaparecidos"]] + [""]
    if log.get("costo_api"):
        c = log["costo_api"]
        lineas += ["### Costo de clasificacion", "",
                   f'- {c["llamadas"]} llamadas · {c["entrada"]} tok entrada · '
                   f'{c["salida"]} tok salida · {c["cache_lectura"]} tok leidos de cache', ""]

    ruta = DIR_CORRIDAS / f'{log["fecha"]}.md'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    previo = ruta.read_text(encoding="utf-8") if ruta.exists() else f'# Corrida {log["fecha"]}\n'
    ruta.write_text(previo.rstrip() + "\n\n" + "\n".join(lineas), encoding="utf-8")
    return ruta


if __name__ == "__main__":
    _sz = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--solo-zonas=")), None)
    l = correr(sin_red="--sin-red" in sys.argv, sin_api="--sin-api" in sys.argv,
               desde_cache="--desde-cache" in sys.argv,
               solo_zonas=[z.strip() for z in _sz.split(",") if z.strip()] if _sz else None)
    # Paso 10: tres lineas, sin inflar el reporte.
    r = l.get("resumen", {})
    print(f'{len(l["altas"])} avisos nuevos.')
    print(f'{r.get("por_seccion", {}).get("candidatos", 0)} pasaron los filtros.')
    caidos = [d for d in l["desaparecidos"] if d["era_favorito"]]
    if caidos:
        print(f'ATENCION: se cayo un favorito -> {caidos[0]["direccion"]}')
    elif not l["altas"]:
        print("Hoy no hay nada.")
