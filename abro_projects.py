"""Proyectos ABRO del MCP: archivos JSON locales (no son el .db).

ABRO de escritorio no expone API ni guarda proyectos en abro.db (solo tablas de
referencia). Este módulo persiste los casos de estudio del MCP en
ABRO_PROJECTS_DIR/*.json para luego generar reportes o subirlos al Ministerio.
"""
import json
import os
from datetime import datetime
from pathlib import Path

DEFAULT_DIR = r"D:\ATI CAMARGO\MCP ABRO\proyectos"


def projects_dir() -> Path:
    d = Path(os.environ.get("ABRO_PROJECTS_DIR", DEFAULT_DIR))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(nombre: str) -> str:
    keep = "".join(c if (c.isalnum() or c in "-_") else "_" for c in nombre)
    return (keep or "proyecto")[:60]


def guardar(nombre: str, datos: dict) -> dict:
    d = projects_dir()
    fname = f"{datetime.now():%Y%m%d_%H%M%S}_{_safe_name(nombre)}.json"
    payload = {
        "nombre": nombre,
        "guardado_en": datetime.now().isoformat(timespec="seconds"),
        "abro_version": "4.0.1",
        "datos": datos,
    }
    (d / fname).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"archivo": fname, "ruta": str(d / fname)}


def cargar(archivo: str) -> dict:
    p = projects_dir() / archivo
    if not p.exists():
        raise FileNotFoundError(f"Proyecto no encontrado: {archivo}")
    return json.loads(p.read_text(encoding="utf-8"))


def listar() -> list[dict]:
    d = projects_dir()
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append({"archivo": p.name, "nombre": data.get("nombre"),
                        "guardado_en": data.get("guardado_en"),
                        "size_bytes": p.stat().st_size})
        except Exception:
            out.append({"archivo": p.name, "nombre": None, "guardado_en": None,
                        "size_bytes": p.stat().st_size})
    return out
