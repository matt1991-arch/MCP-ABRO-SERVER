# AGENTS.md — Guía del repositorio abro-mcp-server

> Instrucciones para agentes (OpenCode, Claude Code, Cursor, etc.) y
> colaboradores que trabajen en este repo o generen archivos `.abro` con él.
> Lee este archivo completo antes de modificar código o tocar un `.abro`.

## 1. Qué es esto

Servidor **MCP por `stdio`** (Python + FastMCP) que conecta al programa
**ABRO 4.0.1** del MMAyA (app de escritorio Qt + SQLite, sin API):

- Lee `abro.db` en modo solo-lectura (`mode=ro`) para no bloquear a `Abro.exe`.
- Expone catálogos (zonas, suelos, cultivos, cuencas, ubicación) y cálculos del
  Manual Técnico (Pe, eficiencias, ETo Penman-Monteith FAO-56, dotación, balance).
- Guarda casos de estudio como JSON en `./proyectos/`.

Con este repo + ABRO se generan archivos `.abro` de atajados con balance
funcional (ver sección 4, el flujo completo).

## 2. Mapa del repo

| Archivo | Propósito |
|---|---|
| `server.py` | Servidor FastMCP (19 tools). Carga `.env` local sin dependencias. Punto de entrada: `python server.py` (stdio). |
| `abro_db.py` | Conexión y consultas a `abro.db` (lee `ABRO_DB_PATH`, `ABRO_ALLOW_WRITE`). |
| `abro_calc.py` | Cálculos Manual Técnico / FAO-56. |
| `abro_projects.py` | Guardar/cargar/listar proyectos JSON (`ABRO_PROJECTS_DIR`). |
| `requirements.txt` | `mcp>=1.20.0`, `pydantic>=2.0`. |
| `.env.example` | Plantilla de variables. **Nunca subir `.env`** (rutas locales). |
| `mcp.json.example` | Plantilla de registro para clientes MCP. **Nunca subir `mcp.json`** (rutas locales). |
| `proyectos/20261004_111550_ejemplo_camargo.json` | Único JSON publicado (ejemplo genérico). Los casos reales **no se suben**. |

Archivos que viven **fuera del repo** y usa el flujo `.abro`:

- `%TEMP%\opencode\abro_app.jar` — backend Java extraído de `Abro.exe` (para sellar con `jjs` de Java 8).
- `%TEMP%\opencode\build_*.py` — scripts que construyen cada atajado desde el origen.
- `%TEMP%\opencode\sellar_*.js`, `verificar_todos.js` — sellado y verificación con las clases reales (`DocumentoABRO`, `Util`).
- `BALANCE HIDRICO\BALANCE FINAL\*.abro` — los 5 atajados funcionales (datos de proyecto, no publicar).

## 3. Servidor MCP

```bat
pip install -r requirements.txt
copy .env.example .env   & rem editar rutas
python server.py         & rem stdio: initialize → tools/list → tools/call
```

Variables: `ABRO_DB_PATH` (ruta a `abro.db`), `ABRO_ALLOW_WRITE` (`0` lectura /
`1` escritura vía `abro_sql_write`), `ABRO_PROJECTS_DIR` (JSON de proyectos).

19 tools: `abro_estado`, `abro_tablas`, `abro_consultar`, `abro_sql_select`,
`abro_sql_write`, `abro_zonas`, `abro_suelos`, `abro_cultivos_por_zona`,
`abro_buscar_cultivo`, `abro_ubicacion`, `abro_cuencas`,
`calc_precipitacion_efectiva`, `calc_eficiencias`, `calc_eto`,
`calc_dotacion`, `calc_balance`,
`proyecto_guardar`, `proyecto_cargar`, `proyecto_listar`.

## 4. Flujo de trabajo .abro (cómo sale todo)

Así se generaron los 5 atajados funcionales. Seguirlo en orden; saltarse un
paso produce archivos "dañados" o balances que no calculan.

### 4.1 Origen

Todo parte de **`atajado el abra duraznera.abro`** (archivo sano verificado).
Cada atajado nuevo se construye copiando sus bytes y aplicando solo los
cambios de datos (comunidad, áreas, oferta, fecha, familias). Plantilla:
`%TEMP%\opencode\build_charco.py` (clonar y adaptar por atajado).

Cédula estándar: 5 cultivos CP + 5 SP (papa temprana, 3 duraznos
BLANCO/AMARILLO/CRIOLLO, haba seca), reparto **90% perenne / 10% verano**,
`UUID`s únicos por fila, oferta con patrón `m1–m5,m8–m11` uniforme,
`m12` = ajuste de cierre, `m6=m7=0`.
**OJO: en la matriz de oferta `m1` = ENERO** (no junio aunque otras
listas del XML vayan jun→may; la UI lo confirma mes a mes).
`m6=m7=0` = jun–jul (invierno, sin demanda). Nunca poner en cero
ene–may: el balance falla y Vol. usado sale 0.

### 4.2 Reglas de edición (aprendidas a golpes, no negociables)

1. **Edición por texto puro** (Python, UTF-8, `newline=''`, se preserva LF).
   Nunca reescribir el XML con `ElementTree.write` (cambia comillas,
   declaración y fines de línea y JAXB lo rechaza).
2. **NO tocar**: `nombreProyecto` (título largo del proyecto, NO la
   comunidad), `codigoControl`, `departamentoDTO`, clima, eficiencias,
   `versionDB`, declaración XML
   (`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`).
   La comunidad vive solo en `comunidades/listaComunidades`.
3. **Máximo 2 decimales** en todo número que pisa el usuario (áreas, oferta).
   Los validadores JavaFX rechazan 3+ decimales y el balance no calcula.
4. **`areaRegable` se deja vacío** (como duraznera): JAXB/ABRO trunca `0.52`
   a `0.5` al guardar. El área real la toman las filas de cultivo.
5. **Nunca PowerShell para texto con Ñ** (mojibake garantizado): usar
   Python/`jjs` (JAXB) para todo lo que toque el archivo.
6. Los `balance_*` y `resumenBalanceCP` guardados son **heredados/stale**:
   la demanda real solo existe tras calcular en ABRO (4.4). No intentar
   calcularlos a mano.

### 4.3 Sellado (jjs + clases reales)

```bat
jjs -cp abro_app.jar sellar_<atajado>.js
```

El script hace: unmarshal → `version = codigoControl` → `version =
SHA256(marshal)` → reescribe canónico JAXB → verifica. Plantilla:
`%TEMP%\opencode\sellar_tembla.js` (41 líneas, con verificación).

> Nota: ese script imprime `validacion version: FALLA` por un bug en su
> propia línea de chequeo (compara contra el valor recién pisado).
> **Ignorarlo** y verificar con `verificar_todos.js`, que implementa el
> chequeo real de apertura.

### 4.4 Verificación (criterio de aceptación)

```bat
jjs -cp abro_app.jar verificar_todos.js
```

Cada archivo debe dar **`codigoControl: OK` + `version: OK`**, donde:
`codigoControl = SHA256(generarCodigoControl())` y
`version = SHA256(marshal con version=codigoControl)`.
Si algo falla → no abrir en ABRO, reconstruir (4.1–4.3).

### 4.5 Activación del balance en ABRO (procedimiento, en orden)

Los campos Vol. previsto / Vol. usado / Caudal / Capacidad de red **no
existen en el XML**: son cálculos en vivo que exigen la cadena completa,
porque Demanda arma el calendario de cultivos en memoria:

1. Abrir el `.abro`.
2. **Cálculo ETo → Calcular** (12 valores).
3. **Demanda → Calcular** (curvas Kc + tabla mensual de los 5 cultivos).
4. **Balance → Calcular** (se llena el resumen; Vol. previsto = oferta anual).

Ir directo al Balance sin el paso 3 imprime *"No se tiene un calculo para
balance"* y vacía el resumen. Si Demanda muestra un error, reportar el
mensaje exacto (suele ser validación de fechas vs ciclo del cultivo).

## 5. Git (qué se sube y qué no)

- ✅ Código, `README.md`, `AGENTS.md`, `.env.example`, `mcp.json.example`, ejemplo genérico.
- ❌ `.env`, `mcp.json` (rutas locales), `__pycache__/`, JSON reales de
  `proyectos/`, `.abro` (datos de proyecto, repo público), `abro.db`/`.exe`.
- Rama `main`. Commits en español, concisos.

## 6. Compatibilidad con otros CLI

El servidor es MCP estándar por `stdio`: funciona sin cambios en Claude
Desktop, Claude Code, OpenCode, Cursor, Windsurf, VS Code y Gemini CLI.
Solo cambia el archivo donde cada cliente registra `command + args + env`
(ver ejemplos en `README.md`). No agregar código específico por cliente.
