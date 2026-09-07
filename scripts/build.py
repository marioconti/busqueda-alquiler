"""Regenera web/data.js a partir de data/*.json.

No hay build step ni framework: data.js es un unico archivo que define window.DATOS y el
index.html lo levanta con un <script>. Asi la pagina abre con doble click, sin servidor.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eventos  # noqa: E402
from lib_config import (DIR_DATA, DIR_WEB, asignar_numeros, escribir_json,  # noqa: E402
                        leer_json, load_config, normalizar_direccion)
from score import clave_orden_default, procesar  # noqa: E402


def _fusionar_analisis(avisos: list[dict], analisis: dict) -> None:
    for a in avisos:
        info = analisis.get(a["id"])
        if not info:
            continue
        for k, v in info.items():
            a[k] = v


def _resumen(avisos: list[dict], descartados: list[dict]) -> dict:
    por_seccion: dict[str, int] = {}
    for a in avisos:
        por_seccion[a["seccion"]] = por_seccion.get(a["seccion"], 0) + 1
    por_motivo: dict[str, int] = {}
    for d in descartados:
        # Tres estados distintos, y confundirlos vacia el bucle de aprendizaje:
        #   categoria puesta            -> el patron se puede contar
        #   sin categoria pero CON texto-> hay algo que leer y clasificar despues
        #   sin categoria y SIN texto   -> `sin_motivo`: Mario no quiso decirlo (2026-08-24)
        # El tercero no es un caso del segundo: uno es dato por clasificar, el otro es
        # dato que no existe. Metidos en el mismo balde, "sin_categoria" crece y no se
        # sabe si es trabajo pendiente o silencio deliberado.
        m = (d.get("motivo_categorizado")
             or ("sin_categoria" if (d.get("motivo_literal") or "").strip() else "sin_motivo"))
        por_motivo[m] = por_motivo.get(m, 0) + 1
    por_barrio: dict[str, int] = {}
    for a in avisos:
        b = a.get("barrio") or "sin barrio"
        por_barrio[b] = por_barrio.get(b, 0) + 1
    # POR PORTAL, y solo sobre la LISTA CORTA. El total por portal no dice nada util
    # (Zonaprop gana siempre por volumen); lo que se quiere saber es cuanto aporta cada
    # uno a lo que se mira. Mario pregunto "no veo nada de mercado libre" teniendo 69 de
    # 202 en la lista corta: el dato existia y no estaba en ningun lado de la pagina.
    corta_portal: dict[str, int] = {}
    for a in avisos:
        if a.get("seccion") in ("favoritos", "candidatos", "al_limite")                 and a.get("estado_aviso") != "desaparecido":
            k = a.get("portal") or "sin portal"
            corta_portal[k] = corta_portal.get(k, 0) + 1

    sin_verificar = sum(1 for a in avisos if a.get("estado_aviso") == "vigente_sin_verificar")
    parciales = sum(1 for a in avisos if a.get("score_desglose", {}).get("parcial"))
    sin_fotos = sum(1 for a in avisos if not a.get("fotos"))
    sin_estado = sum(1 for a in avisos if not a.get("estado_visual"))
    cobertura = [a.get("score_desglose", {}).get("cobertura", 0) for a in avisos]
    return {
        "total_avisos": len(avisos),
        "por_seccion": por_seccion,
        "por_barrio": por_barrio,
        "lista_corta_por_portal": corta_portal,
        "descartados": len(descartados),
        "descartados_por_motivo": por_motivo,
        "sin_verificar": sin_verificar,
        "score_parcial": parciales,
        "sin_fotos": sin_fotos,
        "sin_estado_visual": sin_estado,
        "cobertura_media": round(sum(cobertura) / len(cobertura)) if cobertura else 0,
    }


def _refrescar_dias_publicado(avisos: list[dict]) -> None:
    """`publicado_hace_dias` es relativo al dia en que se leyo: guardado tal cual, un
    aviso que no vuelve a salir en un barrido sigue diciendo "hace 2 dias" para siempre.
    La fecha absoluta (`publicado_el`) es el dato duro; los dias se recalculan aca."""
    hoy = date.today()
    for a in avisos:
        if not a.get("publicado_el"):
            continue
        try:
            # [:10] porque la ficha guarda ISO completo ("2026-08-11T09:12:00Z") y el
            # listado guarda solo la fecha. Los dos formatos tienen que entrar.
            y, m, d = (int(x) for x in str(a["publicado_el"])[:10].split("-"))
        except (ValueError, AttributeError):
            continue
        a["publicado_hace_dias"] = (hoy - date(y, m, d)).days


def build() -> dict:
    cfg = load_config()
    doc_avisos = leer_json(DIR_DATA / "avisos.json")
    doc_desc = leer_json(DIR_DATA / "descartados.json", {"descartados": []})
    doc_fav = leer_json(DIR_DATA / "favoritos.json", {"favoritos": []})
    doc_ana = leer_json(DIR_DATA / "analisis.json", {"analisis": {}})
    doc_vis = leer_json(DIR_DATA / "visitas.json", {"visitas": []})

    avisos = doc_avisos["avisos"]
    nuevos_num = asignar_numeros(doc_avisos)
    if nuevos_num:
        escribir_json(DIR_DATA / "avisos.json", doc_avisos)  # el numero tiene que persistir

    # ANTES de puntuar, no despues. El estado visual es el criterio de mayor peso (20) y
    # ademas el primer desempate del orden: fusionarlo despues de procesar() significaba
    # que el score nunca lo veia. Se ordenaba por un dato que no habia entrado en la cuenta.
    import clasificar  # import tardio: clasificar importa score
    clasificar.fusionar_en(avisos)

    _refrescar_dias_publicado(avisos)
    procesar(avisos, cfg)
    _fusionar_analisis(avisos, doc_ana.get("analisis", {}))

    for a in avisos:
        if not a.get("direccion_norm"):
            a["direccion_norm"] = normalizar_direccion(a.get("direccion"))

    avisos.sort(key=clave_orden_default)

    payload = {
        "generado": date.today().isoformat(),
        "eventos": eventos.leer()[-300:],
        "config": cfg,
        "meta_avisos": doc_avisos.get("meta", {}),
        "avisos": avisos,
        "descartados": doc_desc.get("descartados", []),
        "meta_descartados": doc_desc.get("meta", {}),
        "favoritos": doc_fav.get("favoritos", []),
        "visitas": doc_vis.get("visitas", []),
        "resumen": _resumen(avisos, doc_desc.get("descartados", [])),
    }

    DIR_WEB.mkdir(parents=True, exist_ok=True)
    salida = DIR_WEB / "data.js"
    salida.write_text(
        "// GENERADO POR scripts/build.py - NO EDITAR A MANO\n"
        "window.DATOS = " + json.dumps(payload, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )
    return payload["resumen"]


if __name__ == "__main__":
    r = build()
    print("web/data.js regenerado")
    print(f'  avisos: {r["total_avisos"]}  ->  {r["por_seccion"]}')
    print(f'  descartados: {r["descartados"]}  ->  {r["descartados_por_motivo"]}')
    print(f'  sin verificar vigencia: {r["sin_verificar"]}   score parcial: {r["score_parcial"]}')
