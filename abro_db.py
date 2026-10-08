"""Capa de acceso a abro.db (SQLite, Qt + SQLite, app de escritorio sin API)."""
import os
import sqlite3
from pathlib import Path

# Tablas conocidas de ABRO 4.0.1 (whitelist para consultas y escritura controlada)
ALLOWED_TABLES = {
    "condicionAgroclimatica",
    "cuencaAporte",
    "cuencaNivel",
    "cultivoEspecial",
    "cultivoEspecialDetalle",
    "departamento",
    "etFig29",
    "etFig30a",
    "etFig30b",
    "etFig32a",
    "etFig32b",
    "etFig32c",
    "kcMesFechas",
    "kcMesFechasProceso",
    "laminaInfiltrada",
    "municipio",
    "parametroZonaAgroecologica",
    "provincia",
    "tipoFuenteOferta",
    "tipoPendiente",
    "tipoSuelo",
    "versionDB",
    "zona",
}

DEFAULT_DB = r"D:\ATI CAMARGO\3ER PRODUCTO\BALANCE HIDRICO\Abro 4.0.1\Abro 4.0.1\abro.db"


def db_path() -> str:
    p = os.environ.get("ABRO_DB_PATH", DEFAULT_DB)
    if not Path(p).exists():
        raise FileNotFoundError(f"No se encuentra abro.db en: {p}")
    return p


def allow_write() -> bool:
    return os.environ.get("ABRO_ALLOW_WRITE", "0") == "1"


def connect(read_only: bool = True) -> sqlite3.Connection:
    """Conecta a abro.db. Por defecto en modo read-only (URI mode=ro)
    para no bloquear ni modificar el archivo original que usa Abro.exe."""
    path = db_path()
    if read_only:
        uri = "file:" + path.replace("\\", "/") + "?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=10)
    else:
        if not allow_write():
            raise PermissionError("Escritura deshabilitada (ABRO_ALLOW_WRITE!=1)")
        con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def list_tables() -> list[dict]:
    con = connect(True)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        out = []
        for (name,) in rows:
            try:
                cnt = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except Exception:
                cnt = -1
            out.append({"tabla": name, "filas": cnt})
        return out
    finally:
        con.close()


def table_columns(table: str) -> list[dict]:
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Tabla no permitida: {table}")
    con = connect(True)
    try:
        cols = con.execute(f'PRAGMA table_info("{table}")').fetchall()
        return [{"cid": c[0], "nombre": c[1], "tipo": c[2]} for c in cols]
    finally:
        con.close()


def select_table(table: str, where_like: str = "", limit: int = 50) -> list[dict]:
    """Consulta simple con filtro LIKE opcional aplicado a columnas TEXT."""
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Tabla no permitida: {table}")
    limit = max(1, min(int(limit), 500))
    con = connect(True)
    try:
        cols = [c[1] for c in con.execute(f'PRAGMA table_info("{table}")').fetchall()]
        text_cols = cols  # LIKE sobre concatenación simple
        if where_like:
            # Búsqueda en todas las columnas como texto (escape comillas)
            like = "%" + where_like.replace("'", "''") + "%"
            conds = " OR ".join([f'CAST("{c}" AS TEXT) LIKE ?' for c in cols])
            sql = f'SELECT * FROM "{table}" WHERE {conds} LIMIT {limit}'
            params = [like] * len(cols)
            rows = con.execute(sql, params).fetchall()
        else:
            rows = con.execute(f'SELECT * FROM "{table}" LIMIT {limit}').fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def safe_select(sql: str, limit: int = 200) -> list[dict]:
    """Ejecuta un SELECT arbitrario con guardrails: solo SELECT, sin ATTACH/PRAGMA escritura."""
    s = sql.strip()
    low = s.lower()
    if not low.startswith("select") and not low.startswith("with"):
        raise ValueError("Solo se permiten consultas SELECT/WITH")
    banned = ["insert", "update", "delete", "drop", "alter", "attach", "detach",
              "vacuum", "pragma", "write", "replace"]
    # permite la palabra dentro de strings? chequeo simple por tokens fuera de comillas
    import re
    code = re.sub(r"'[^']*'", "", low)
    for b in banned:
        if re.search(rf"\b{b}\b", code):
            raise ValueError(f"Palabra no permitida en SELECT: {b}")
    con = connect(True)
    try:
        rows = con.execute(s).fetchmany(int(limit))
        return [dict(r) for r in rows]
    finally:
        con.close()


def exec_write(sql: str) -> dict:
    """Ejecuta INSERT/UPDATE/DELETE sobre tablas permitidas. Requiere ABRO_ALLOW_WRITE=1."""
    if not allow_write():
        raise PermissionError("Escritura deshabilitada (ABRO_ALLOW_WRITE!=1)")
    s = sql.strip()
    low = s.lower()
    import re
    m = re.match(r"\s*(insert\s+into|update|delete\s+from)\s+[\"'\[]?(\w+)", low)
    if not m:
        raise ValueError("Solo INSERT/UPDATE/DELETE")
    # extraer nombre real de tabla de forma robusta
    tbl = re.match(r'\s*(?:insert\s+into|update|delete\s+from)\s+["\'\[]?(\w+)', s, re.I)
    if not tbl or tbl.group(1) not in ALLOWED_TABLES:
        raise ValueError("Tabla no permitida para escritura")
    if tbl.group(1) == "versionDB":
        raise ValueError("versionDB es de solo lectura")
    con = connect(False)
    try:
        cur = con.execute(s)
        con.commit()
        return {"tabla": tbl.group(1), "filas_afectadas": cur.rowcount}
    finally:
        con.close()
