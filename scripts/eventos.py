"""Bitacora de eventos: el unico lugar donde se escriben tus decisiones.

EL PROBLEMA QUE RESUELVE
------------------------
Antes las decisiones vivian mezcladas con los datos scrapeados dentro de avisos.json.
Eso tiene una falla que tarde o temprano duele: **un re-scrapeo te puede pisar una
decision**. Si manana la ficha vuelve a bajarse y sobreescribe el aviso, el "descartado
porque se ve viejo" se va con ella.

LA SEPARACION
-------------
    data/avisos.json     HECHOS.      Los escriben detalle.py / parse.py / reglas.py.
                                      Se pueden borrar y volver a bajar sin perder nada.
    data/eventos.jsonl   DECISIONES.  Las escribis vos (desde la pagina o por chat).
                                      Append-only. NADA las pisa. NADA las borra.

El estado que ve la pagina es la fusion de los dos: hechos + replay de la bitacora.
Como el replay es deterministico, el estado se puede reconstruir entero desde cero en
cualquier momento. Esa es la propiedad que hace que esto no necesite una base de datos.

POR QUE JSONL Y NO EXCEL / CSV / SQLITE
---------------------------------------
- Es append-only: escribir es agregar una linea. No hay forma de corromper lo anterior.
- Dos procesos pueden agregar sin pisarse.
- Se lee con la vista y se versiona con git si algun dia queres.
- Excel BLOQUEA el archivo mientras lo tenes abierto: si la corrida diaria intenta
  escribir con la planilla abierta, falla. Y Excel reformatea solo (fechas, numeros con
  punto, acentos en CSV). Como SUPERFICIE DE LECTURA es comodo, y para eso esta
  `exportar_csv()` mas abajo. Como lugar donde se escribe, es una trampa.

USO DESDE EL CHAT (esto es lo que me permite a mi actualizar la pagina cuando me contas algo)
    python scripts/eventos.py descarte zp-59818437 "muy sobre la avenida"
    python scripts/eventos.py vista_online zp-59773617
    python scripts/eventos.py nota zp-49100787 "el dueno pide destino del alquiler"
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import (DIR_DATA, escribir_json, leer_json,  # noqa: E402
                        normalizar_direccion, por_numero)

RUTA = DIR_DATA / "eventos.jsonl"

TIPOS = {
    "favorito":      "marcado como me interesa",
    "no_favorito":   "sacado de favoritos (sin descartarlo)",
    "descarte":      "descartado (el motivo es opcional)",
    "vista_online":  "ya la vi por internet, no mostrar arriba",
    "revivir":       "sacar de descartados y volver a considerar",
    "visita":        "fui a verla, con notas",
    "nota":          "anotacion libre sobre un aviso",
    "contacto":      "escribi/llame a una inmobiliaria",
    "prioridad":     "orden de visita",
    "corrida":       "resultado de una corrida (lo escribe main.py)",
}


# --------------------------------------------------------------------------- escritura

def registrar(tipo: str, id_aviso: str | None = None, origen: str = "chat", **campos) -> dict:
    if tipo not in TIPOS:
        raise ValueError(f"tipo desconocido: {tipo}. Validos: {', '.join(TIPOS)}")
    ev = {"ts": datetime.now().isoformat(timespec="seconds"), "tipo": tipo,
          "origen": origen, "id": id_aviso, **campos}
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    with RUTA.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return ev


def resolver(ref: str) -> tuple[str | None, str | None]:
    """Acepta '#7', '7' o 'zp-59818437' y devuelve (id, direccion).

    Existe para que desde el chat se pueda escribir  `eventos.py descarte 7 "motivo"`
    con el mismo numero que Mario ve en la pagina.
    """
    ref = (ref or "").strip().lstrip("#")
    doc = leer_json(DIR_DATA / "avisos.json", {"avisos": []})
    if ref.isdigit():
        a = por_numero(doc, int(ref))
        if not a:
            raise SystemExit(f"no hay ningun aviso con el numero #{ref}")
        return a["id"], a.get("direccion")
    for a in doc["avisos"]:
        if a.get("id") == ref:
            return a["id"], a.get("direccion")
    return ref, None


def leer() -> list[dict]:
    if not RUTA.exists():
        return []
    out = []
    for linea in RUTA.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            out.append(json.loads(linea))
        except json.JSONDecodeError:
            continue  # una linea rota no se lleva puesta la bitacora entera
    return out


# --------------------------------------------------------------------------- replay

def aplicar(doc_avisos: dict, eventos: list[dict] | None = None) -> dict:
    """Reproduce la bitacora sobre los hechos. Deterministico e idempotente.

    Reproducir dos veces la misma bitacora da el mismo resultado, y reproducirla entera
    desde cero reconstruye el estado completo. Por eso los derivados (favoritos.json,
    descartados.json) no hace falta cuidarlos: se regeneran.
    """
    eventos = eventos if eventos is not None else leer()
    por_id = {a["id"]: a for a in doc_avisos["avisos"]}
    descartes, favoritos, visitas, contactos = {}, {}, [], []

    # Reset de los campos que son PROPIEDAD de la bitacora. Sin esto, borrar o corregir
    # un evento no revierte nada: el aviso se queda con la decision vieja pegada y el
    # replay deja de ser reproducible. Todo lo que se resetea aca se vuelve a poner
    # abajo a partir de los eventos, y nada mas lo escribe.
    for a in doc_avisos["avisos"]:
        for campo in ("decision", "pinned", "vista_online", "vista_online_el",
                      "visitada", "notas_mario"):
            a.pop(campo, None)

    def clave(ev_o_dic, direccion=None):
        """Los descartes de la semilla no tienen id (Mario los anoto por direccion)."""
        i = ev_o_dic.get("id")
        if i:
            return i
        d = direccion or ev_o_dic.get("direccion")
        return "dir:" + (normalizar_direccion(d) or str(d))

    for ev in sorted(eventos, key=lambda e: e.get("ts", "")):
        a = por_id.get(ev.get("id"))
        t = ev["tipo"]
        k = clave(ev)

        if t == "favorito":
            if a:
                a["decision"] = "favorito"
                a["pinned"] = True
            favoritos[k] = {
                "id": ev.get("id"), "direccion": ev.get("direccion") or (a or {}).get("direccion"),
                "agregado": ev["ts"][:10], "nota": ev.get("nota"),
                "prioridad_visita": favoritos.get(k, {}).get("prioridad_visita"),
                "ultima_verificacion": (a or {}).get("ficha_leida_el")}
            descartes.pop(k, None)

        elif t == "descarte":
            direccion = ev.get("direccion") or (a or {}).get("direccion")
            if a:
                a["decision"] = "descartado"
                a["pinned"] = False
            descartes[k] = {
                "id": ev.get("id"), "direccion": direccion,
                "direccion_norm": normalizar_direccion(direccion),
                "barrio": ev.get("barrio") or (a or {}).get("barrio"),
                "precio_usd": ev.get("precio_usd") or (a or {}).get("precio_total_usd"),
                "fecha_descarte": ev["ts"][:10],
                "motivo_literal": ev.get("motivo"),
                "motivo_literal_verbatim": ev.get("verbatim", True),
                "motivo_categorizado": ev.get("categoria"),
                "atributos": ev.get("atributos") or {},
                "aprendizaje": ev.get("aprendizaje"),
                "reversible": ev.get("reversible", True),
                "es_regla": ev.get("es_regla", False),
                "accion_pendiente": ev.get("accion_pendiente"),
                "nota_de_consistencia": ev.get("nota_de_consistencia")}
            favoritos.pop(k, None)

        elif t == "no_favorito":
            if a:
                a["pinned"] = False
                a["decision"] = None
            favoritos.pop(k, None)

        elif t == "revivir":
            descartes.pop(k, None)

        elif t == "vista_online" and a:
            a["vista_online"] = True
            a["vista_online_el"] = ev["ts"][:10]

        elif t == "prioridad" and k in favoritos:
            favoritos[k]["prioridad_visita"] = ev.get("prioridad")

        elif t == "visita":
            visitas.append({k: v for k, v in ev.items() if k != "origen"})
            if a:
                a["visitada"] = True

        elif t == "nota" and a:
            a.setdefault("notas_mario", []).append({"fecha": ev["ts"][:10], "texto": ev.get("texto")})

        elif t == "contacto":
            contactos.append({k: v for k, v in ev.items() if k != "origen"})

    return {"avisos": list(por_id.values()), "descartados": list(descartes.values()),
            "favoritos": list(favoritos.values()), "visitas": visitas, "contactos": contactos}


def sembrar_desde_semilla() -> int:
    """Convierte la semilla cargada a mano en eventos. Se corre UNA vez; es idempotente.

    Por que hace falta: si los 12 favoritos y los 37 descartes viven solo en los JSON
    derivados y no en la bitacora, el replay no puede reconstruirlos, y entonces no
    puede resetear nada sin borrarlos. Metiendo la semilla en la bitacora, la bitacora
    pasa a ser el registro COMPLETO de decisiones y los derivados quedan 100% derivados.
    """
    if any(e.get("origen") == "semilla" for e in leer()):
        return 0

    doc = leer_json(DIR_DATA / "avisos.json")
    desc = leer_json(DIR_DATA / "descartados.json", {"descartados": []})
    n = 0

    for a in doc["avisos"]:
        if not a.get("pinned"):
            continue
        registrar("favorito", a["id"], origen="semilla", direccion=a.get("direccion"),
                  barrio=a.get("barrio"), precio_usd=a.get("precio_total_usd"),
                  url=a.get("url"))
        n += 1

    for d in desc["descartados"]:
        registrar("descarte", d.get("id"), origen="semilla",
                  direccion=d.get("direccion"), barrio=d.get("barrio"),
                  precio_usd=d.get("precio_usd"), motivo=d.get("motivo_literal"),
                  verbatim=d.get("motivo_literal_verbatim", False),
                  categoria=d.get("motivo_categorizado"),
                  atributos=d.get("atributos") or {}, aprendizaje=d.get("aprendizaje"),
                  reversible=d.get("reversible", True), es_regla=d.get("es_regla", False),
                  accion_pendiente=d.get("accion_pendiente"),
                  nota_de_consistencia=d.get("nota_de_consistencia"))
        n += 1
    return n


def sincronizar() -> dict:
    """Replay + reescritura de los derivados. Es lo que corre antes de cada build.

    Los derivados (descartados.json, favoritos.json, visitas.json) se REESCRIBEN
    enteros desde la bitacora. Si se pierden, se regeneran. Lo unico irreemplazable es
    data/eventos.jsonl.
    """
    doc = leer_json(DIR_DATA / "avisos.json")
    meta_desc = leer_json(DIR_DATA / "descartados.json", {"meta": {}}).get("meta", {})
    meta_fav = leer_json(DIR_DATA / "favoritos.json", {"meta": {}}).get("meta", {})
    meta_vis = leer_json(DIR_DATA / "visitas.json", {"meta": {}}).get("meta", {})

    r = aplicar(doc)
    escribir_json(DIR_DATA / "avisos.json", doc)
    escribir_json(DIR_DATA / "descartados.json", {"meta": meta_desc, "descartados": r["descartados"]})
    escribir_json(DIR_DATA / "favoritos.json", {"meta": meta_fav, "favoritos": r["favoritos"]})
    if r["visitas"]:
        escribir_json(DIR_DATA / "visitas.json", {"meta": meta_vis, "visitas": r["visitas"]})
    return {"eventos": len(leer()), "descartes": len(r["descartados"]),
            "favoritos": len(r["favoritos"]), "visitas": len(r["visitas"])}


# --------------------------------------------------------------------------- csv

def exportar_csv(destino: Path | None = None) -> Path:
    """Planilla plana para abrir en Excel. SOLO LECTURA: no se vuelve a importar.

    Es la respuesta a "un excel que vos vayas completando": sirve para mirar, ordenar,
    filtrar y llevartelo. Lo que NO hace es ser el lugar donde se escribe (ver el
    encabezado de este archivo).
    """
    import csv

    destino = destino or (DIR_DATA / "propiedades.csv")
    doc = leer_json(DIR_DATA / "avisos.json")
    cols = ["direccion", "barrio", "tipo", "precio_total_usd", "m2_cubiertos",
            "m2_descubiertos", "dormitorios_reales", "banos_completos", "estado",
            "antiguedad_anios", "publicado_hace_dias", "dueno_directo", "mascotas",
            "uso_permitido", "score", "score_techo", "decision", "url"]
    with destino.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")   # ; para que Excel en es-AR lo abra en columnas
        w.writerow(cols)
        for a in sorted(doc["avisos"], key=lambda x: -(x.get("score") or 0)):
            fila = []
            for c in cols:
                v = (a.get("score_desglose") or {}).get("score_techo") if c == "score_techo" else a.get(c)
                fila.append("" if v is None else v)
            w.writerow(fila)
    return destino


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("uso: python scripts/eventos.py <tipo> [id] [texto]")
        print("     python scripts/eventos.py sincronizar")
        print("     python scripts/eventos.py csv\n")
        for t, desc in TIPOS.items():
            print(f"  {t:14s} {desc}")
        sys.exit(0)

    if args[0] == "sembrar":
        print(f"{sembrar_desde_semilla()} eventos de semilla")
        print(sincronizar())
    elif args[0] == "sincronizar":
        print(sincronizar())
    elif args[0] == "csv":
        print(f"escrito: {exportar_csv()}")
    else:
        tipo = args[0]
        ref = args[1] if len(args) > 1 else None
        texto = args[2] if len(args) > 2 else None
        categoria = args[3] if len(args) > 3 else None
        # El motivo del descarte es OPCIONAL desde el 2026-08-24. Sigue siendo el dato
        # que alimenta el bucle de aprendizaje, asi que el descarte mudo se etiqueta
        # `sin_motivo` en vez de quedar sin categoria: uno es "no quiso decirlo", el otro
        # es "lo dijo y no lo clasificamos", y contarlos juntos borra la diferencia.
        if tipo == "descarte" and not (texto or "").strip():
            texto = None
            categoria = categoria or "sin_motivo"
        id_aviso, direccion = resolver(ref) if ref else (None, None)
        campo = {"descarte": "motivo", "nota": "texto", "visita": "texto",
                 "contacto": "texto", "prioridad": "prioridad"}.get(tipo)
        extra = {campo: texto} if campo and texto else {}
        if direccion:
            extra["direccion"] = direccion
        if tipo == "descarte" and categoria:
            extra["categoria"] = categoria
        print(registrar(tipo, id_aviso, **extra))
        print(sincronizar())
