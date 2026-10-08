"""MCP ABRO 4.0.1 — Conexión al programa ABRO (MMAyA Bolivia).

ABRO es una app de escritorio Qt + SQLite sin API. Este MCP expone:
- Lectura (y escritura controlada) de abro.db: zonas, suelos, cultivos, cuencas, ubicación.
- Cálculos oficiales del Manual Técnico: Pe, eficiencias, ETo Penman-Monteith FAO-56,
  dotación, balance por campaña.
- Proyectos JSON locales en ./proyectos/ (casos de estudio para reporte/subida al Ministerio).

Ejecución stdio:  python server.py
Env: ABRO_DB_PATH, ABRO_ALLOW_WRITE (0/1), ABRO_PROJECTS_DIR
"""
import os
from pathlib import Path
from typing import Optional

# Carga .env local sin dependencias (para `python server.py` directo)
try:
    _env = Path(__file__).with_name(".env")
    if _env.exists():
        for _line in _env.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
except Exception:
    pass

from mcp.server.fastmcp import FastMCP

import abro_db
import abro_calc
import abro_projects

mcp = FastMCP("abro")


# ---------- Estado y catálogo ----------

@mcp.tool()
def abro_estado() -> dict:
    """Estado de la conexión: ruta db, modo escritura, versión y conteos por tabla."""
    tablas = abro_db.list_tables()
    try:
        ver = abro_db.select_table("versionDB", limit=1)
    except Exception:
        ver = []
    return {
        "db_path": abro_db.db_path(),
        "allow_write": abro_db.allow_write(),
        "versionDB": ver,
        "tablas": tablas,
    }


@mcp.tool()
def abro_tablas() -> dict:
    """Lista tablas de abro.db con conteo de filas y columnas."""
    out = []
    for t in abro_db.list_tables():
        try:
            cols = abro_db.table_columns(t["tabla"])
        except Exception as e:
            cols = [{"error": str(e)}]
        out.append({"tabla": t["tabla"], "filas": t["filas"], "columnas": cols})
    return {"tablas": out}


@mcp.tool()
def abro_consultar(tabla: str, filtro: str = "", limite: int = 50) -> dict:
    """Consulta una tabla permitida con filtro LIKE opcional. Ej: tabla='municipio', filtro='Camargo'."""
    rows = abro_db.select_table(tabla, filtro, limite)
    return {"tabla": tabla, "n": len(rows), "filas": rows}


@mcp.tool()
def abro_sql_select(sql: str, limite: int = 200) -> dict:
    """SELECT libre y seguro sobre abro.db (solo lectura, sin INSERT/UPDATE/DELETE)."""
    rows = abro_db.safe_select(sql, limite)
    return {"n": len(rows), "filas": rows}


@mcp.tool()
def abro_sql_write(sql: str) -> dict:
    """INSERT/UPDATE/DELETE sobre abro.db. Requiere ABRO_ALLOW_WRITE=1. Nunca usar en versionDB."""
    return abro_db.exec_write(sql)


# ---------- Atajos de dominio ----------

@mcp.tool()
def abro_zonas() -> dict:
    """Zonas agroecológicas con umbral y factor de precipitación efectiva."""
    return abro_consultar("zona", limite=10)


@mcp.tool()
def abro_suelos() -> dict:
    """Tipos de suelo con CC, PMP y densidad aparente."""
    return abro_consultar("tipoSuelo", limite=20)


@mcp.tool()
def abro_cultivos_por_zona(zona_nombre_id: str, limite: int = 100) -> dict:
    """Cultivos de parametroZonaAgroecologica filtrados por id/nombre de zona. Ej: '3', 'Valles', 'Altiplano'."""
    # intento 1: LIKE directo
    rows = abro_db.select_table("parametroZonaAgroecologica", zona_nombre_id, limite)
    if rows:
        return {"n": len(rows), "filas": rows}
    # intento 2: resolver nombre de zona -> IdParametro? No hay FK directa; buscar por nombre cultivo
    return {"n": 0, "filas": [], "nota": "Sin coincidencias; usa abro_buscar_cultivo o abro_sql_select"}


@mcp.tool()
def abro_buscar_cultivo(texto: str, limite: int = 50) -> dict:
    """Busca cultivos por nombre en parametroZonaAgroecologica. Ej: 'Papa', 'Maiz', 'Quinua'."""
    return abro_consultar("parametroZonaAgroecologica", texto, limite)


@mcp.tool()
def abro_ubicacion(tipo: str, filtro: str = "", limite: int = 50) -> dict:
    """Ubicación Bolivia: tipo = departamento | provincia | municipio. Ej: tipo='municipio', filtro='Camargo'."""
    t = tipo.lower()
    mapa = {"departamento": "departamento", "provincia": "provincia", "municipio": "municipio"}
    if t not in mapa:
        raise ValueError("tipo debe ser departamento, provincia o municipio")
    return abro_consultar(mapa[t], filtro, limite)


@mcp.tool()
def abro_cuencas(nivel: str = "aporte", filtro: str = "", limite: int = 100) -> dict:
    """Cuencas PNC: nivel='aporte' (55) o 'nivel' (332 unidades hidrográficas nivel 3 y 4)."""
    tabla = "cuencaAporte" if nivel == "aporte" else "cuencaNivel"
    return abro_consultar(tabla, filtro, limite)


# ---------- Cálculos oficiales ----------

@mcp.tool()
def calc_precipitacion_efectiva(pp_mensual: list[float], zona_id: int = 2) -> dict:
    """Pe mensual: (pp-umbral)*factor. zona_id: 1=Chaco, 2=Valles, 3=Altiplano, 5=Trópico. pp en orden jun..may."""
    if len(pp_mensual) != 12:
        raise ValueError("pp_mensual debe tener 12 valores en orden jun..may")
    pe = abro_calc.precipitacion_efectiva_serie([float(x) for x in pp_mensual], int(zona_id))
    return {"zona_id": zona_id, "pp": pp_mensual, "pe": pe,
            "meses": abro_calc.MESES, "total_pe": round(sum(pe), 1)}


@mcp.tool()
def calc_eficiencias(ecap: float, conduccion: list[dict], distribucion: list[dict],
                     metodos_aplicacion: list[dict]) -> dict:
    """Eficiencia total del sistema.

    conduccion/distribucion: [{ef_km: 0.90, longitud_km: 2.5}, ...] (hasta 4 tramos).
    metodos_aplicacion: [{metodo: 'aspersion', porcentaje: 60}, ...] suma 100.
    Métodos: inundacion, surcos, melgas, superficial_mejorado, aspersion, microaspersion, goteo.
    """
    ec = abro_calc.eficiencia_tramos(conduccion)
    ed = abro_calc.eficiencia_tramos(distribucion)
    ea = abro_calc.eficiencia_aplicacion(metodos_aplicacion)
    total = abro_calc.eficiencia_total(float(ecap), ec["eficiencia_total"],
                                      ed["eficiencia_total"], ea["eficiencia_aplicacion"])
    return {"ecap": ecap, "conduccion": ec, "distribucion": ed,
            "aplicacion": ea, "eficiencia_total": total}


@mcp.tool()
def calc_eto(lat_deg: float, alt_msnm: float, datos: list[dict]) -> dict:
    """ETo Penman-Monteith FAO-56 mensual.

    datos: 12 dicts en orden jun..may: {tmax, tmin, hr, nubosidad (0-1), viento}.
    lat_deg negativa al sur de Bolivia (ej -17.4). Retorna ETo mm/día y mm/mes.
    """
    serie = abro_calc.eto_serie_anual(float(lat_deg), float(alt_msnm), datos)
    total_anual = round(sum(r["ETo_mm_mes"] for r in serie), 1)
    return {"serie": serie, "ETo_anual_mm": total_anual}


@mcp.tool()
def calc_dotacion(necesidad_neta_mm: list[float], hectareas: float, eficiencia_total: float) -> dict:
    """Volumen mensual requerido desde fuente: Vd = 10*ha*Nn/Ef. Listas de 12 meses jun..may."""
    if len(necesidad_neta_mm) != 12:
        raise ValueError("necesidad_neta_mm debe tener 12 valores")
    vols = [abro_calc.dotacion_volumen(float(nn), float(hectareas), float(eficiencia_total))
            for nn in necesidad_neta_mm]
    return {"vol_m3": vols, "vol_total_m3": round(sum(vols), 1), "meses": abro_calc.MESES}


@mcp.tool()
def calc_balance(oferta_m3: list[float], demanda_neta_mm: list[float],
                 ha_propuesta: float, eficiencia_total: float) -> dict:
    """Balance hídrico de una campaña (perenne, invierno o verano por separado).

    oferta_m3 y demanda_neta_mm: 12 valores jun..may. Retorna ha calculada,
    mes crítico, volúmenes usados/sobrantes y módulo de riego l/s/ha.
    """
    return abro_calc.balance_campana([float(x) for x in oferta_m3],
                                    [float(x) for x in demanda_neta_mm],
                                    float(ha_propuesta), float(eficiencia_total))


# ---------- Proyectos ----------

@mcp.tool()
def proyecto_guardar(nombre: str, datos: dict) -> dict:
    """Guarda un caso de estudio ABRO como JSON en ./proyectos/."""
    return abro_projects.guardar(nombre, datos)


@mcp.tool()
def proyecto_cargar(archivo: str) -> dict:
    """Carga un proyecto JSON por nombre de archivo."""
    return abro_projects.cargar(archivo)


@mcp.tool()
def proyecto_listar() -> dict:
    """Lista los proyectos guardados en ./proyectos/."""
    return {"proyectos": abro_projects.listar()}


if __name__ == "__main__":
    mcp.run()
