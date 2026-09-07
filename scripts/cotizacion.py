"""Cotizacion del dolar oficial BNA (venta).

El perfil lo pide explicito: "Converti siempre al dolar oficial BNA venta del dia y
guarda la cotizacion usada en el registro, si no los historicos no son comparables".
Guardar la cotizacion es la mitad importante: un precio en USD sin la cotizacion con la
que se calculo no se puede comparar contra el de la semana pasada.

Fuente: dolarapi.com (publica, sin credenciales). Se guarda el historico completo en
data/cotizaciones.json para poder recalcular hacia atras.

Si la API no responde, NO se inventa un valor: se usa la ultima conocida y se marca
`vencida: true`, o se deja que Mario la cargue a mano desde la pagina.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_config import DIR_DATA, escribir_json, leer_json  # noqa: E402

FUENTE = "https://dolarapi.com/v1/dolares/oficial"
RUTA = DIR_DATA / "cotizaciones.json"


def obtener() -> dict | None:
    req = urllib.request.Request(FUENTE, headers={"User-Agent": "busqueda-alquiler/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    venta = d.get("venta")
    if not venta:
        return None
    return {"fecha": date.today().isoformat(), "venta": float(venta),
            "compra": d.get("compra"), "fuente": "dolarapi/oficial",
            "actualizado": d.get("fechaActualizacion")}


def vigente(refrescar: bool = True) -> dict | None:
    """Devuelve la cotizacion de hoy; si no se puede, la ultima conocida marcada vencida."""
    doc = leer_json(RUTA, {"historico": []})
    hoy = date.today().isoformat()
    for c in doc["historico"]:
        if c["fecha"] == hoy:
            return c

    nueva = obtener() if refrescar else None
    if nueva:
        doc["historico"].append(nueva)
        escribir_json(RUTA, doc)
        return nueva

    if doc["historico"]:
        ultima = dict(doc["historico"][-1])
        ultima["vencida"] = True
        return ultima
    return None


def a_usd(monto_ars: float | None, cot: dict | None) -> float | None:
    if monto_ars is None or not cot or not cot.get("venta"):
        return None
    return round(float(monto_ars) / float(cot["venta"]), 0)


def aplicar() -> dict:
    """Recalcula precio_total_usd de todos los avisos con la cotizacion de hoy."""
    cot = vigente()
    doc = leer_json(DIR_DATA / "avisos.json")
    tocados = 0
    for a in doc["avisos"]:
        alq_usd = a.get("precio_alquiler_usd")
        exp_usd = None
        if alq_usd is None and a.get("precio_alquiler_ars") is not None:
            alq_usd = a_usd(a["precio_alquiler_ars"], cot)
            a["cotizacion_usada"] = (cot or {}).get("venta")
            a["cotizacion_fecha"] = (cot or {}).get("fecha")
        if a.get("expensas_ars") is not None:
            exp_usd = a_usd(a["expensas_ars"], cot)
        if alq_usd is None:
            continue
        nuevo = alq_usd + (exp_usd or 0)
        a["expensas_usd"] = exp_usd
        if a.get("precio_total_usd") != nuevo:
            a.setdefault("historial_precio", []).append(
                {"fecha": date.today().isoformat(), "precio_total_usd": nuevo,
                 "fuente": "ficha", "cotizacion": (cot or {}).get("venta")})
        a["precio_total_usd"] = nuevo
        a["precio_incluye_expensas"] = a.get("expensas_declaradas") is True
        tocados += 1

    doc.setdefault("meta", {})["cotizacion_bna_venta"] = (cot or {}).get("venta")
    doc["meta"]["cotizacion_fecha"] = (cot or {}).get("fecha")
    escribir_json(DIR_DATA / "avisos.json", doc)
    return {"cotizacion": cot, "avisos_actualizados": tocados}


if __name__ == "__main__":
    r = aplicar()
    c = r["cotizacion"]
    if not c:
        print("SIN COTIZACION: no se pudo obtener y no hay historico. Cargarla a mano.")
    else:
        marca = " (VENCIDA, es de otro dia)" if c.get("vencida") else ""
        print(f'BNA venta {c["venta"]:.2f} del {c["fecha"]}{marca} · '
              f'{r["avisos_actualizados"]} avisos actualizados')
