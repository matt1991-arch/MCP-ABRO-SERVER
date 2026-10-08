# abro-mcp-server — MCP para el programa ABRO (MMAyA Bolivia)

Servidor [MCP](https://modelcontextprotocol.io/) en Python que conecta al programa
**ABRO 4.0.1** (app de escritorio Qt + SQLite, sin API) mediante lectura directa de
`abro.db` + cálculos oficiales del Manual Técnico + proyectos JSON locales.

Expone:

- Lectura (y escritura controlada) de `abro.db`: zonas, suelos, cultivos, cuencas, ubicación.
- Cálculos oficiales: precipitación efectiva, eficiencias, ETo Penman-Monteith FAO-56,
  dotación, balance por campaña.
- Proyectos JSON locales en `./proyectos/`.

> **Compatibilidad:** es un servidor MCP estándar por `stdio`, así que funciona con
> **cualquier cliente MCP**, no solo OpenCode: Claude Desktop, Claude Code,
> OpenCode, Cursor, Windsurf, VS Code (extensión MCP), Gemini CLI, etc.
> La única configuración necesaria en cada cliente es el comando y las 3 variables
> de entorno de abajo.

## Requisitos

- Python 3.10+
- Acceso de lectura al archivo `abro.db` de tu instalación de ABRO 4.0.1

## Instalación

```bat
git clone https://github.com/matt1991-arch/MCP-ABRO-SERVER.git
cd MCP-ABRO-SERVER
pip install -r requirements.txt
copy .env.example .env
```

Edita `.env` con tus rutas:

```ini
ABRO_DB_PATH=RUTA_A_TU/abro.db
ABRO_ALLOW_WRITE=0
ABRO_PROJECTS_DIR=RUTA_AL_REPO/proyectos
```

- `ABRO_DB_PATH` — ruta a `abro.db` (solo lectura recomendada).
- `ABRO_ALLOW_WRITE=1` — permitir INSERT/UPDATE/DELETE vía `abro_sql_write` (default `0`, solo lectura).
- `ABRO_PROJECTS_DIR` — carpeta de proyectos JSON.

`copy mcp.json.example mcp.json` y ajusta las rutas, o registra el servidor
directamente en tu cliente (ver abajo).

## Registro en clientes MCP

El servidor usa **stdio**: `python server.py` (con el `.env` al lado, o las
variables exportadas). Ejemplos por cliente:

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "abro": {
      "command": "python",
      "args": ["RUTA_AL_REPO/server.py"],
      "env": {
        "ABRO_DB_PATH": "RUTA_A/abro.db",
        "ABRO_ALLOW_WRITE": "0",
        "ABRO_PROJECTS_DIR": "RUTA_AL_REPO/proyectos"
      }
    }
  }
}
```

**OpenCode** (`opencode.json`):

```json
{
  "mcp": {
    "abro": {
      "type": "local",
      "command": ["python", "RUTA_AL_REPO/server.py"],
      "environment": {
        "ABRO_DB_PATH": "RUTA_A/abro.db",
        "ABRO_ALLOW_WRITE": "0",
        "ABRO_PROJECTS_DIR": "RUTA_AL_REPO/proyectos"
      }
    }
  }
}
```

**Claude Code / Cursor / Windsurf / VS Code**: mismo esquema
`command + args + env` en su archivo de configuración MCP
(`.claude.json`, `.cursor/mcp.json`, `mcp.json` según el cliente).

## Herramientas (19)

| Grupo | Herramientas |
|---|---|
| DB lectura | `abro_estado`, `abro_tablas`, `abro_consultar`, `abro_sql_select`, `abro_zonas`, `abro_suelos`, `abro_cultivos_por_zona`, `abro_buscar_cultivo`, `abro_ubicacion`, `abro_cuencas` |
| DB escritura | `abro_sql_write` (solo con `ABRO_ALLOW_WRITE=1`, bloquea `versionDB`) |
| Cálculos | `calc_precipitacion_efectiva`, `calc_eficiencias`, `calc_eto`, `calc_dotacion`, `calc_balance` |
| Proyectos | `proyecto_guardar`, `proyecto_cargar`, `proyecto_listar` |

## Flujo de trabajo .abro (resumen)

Con este repo + ABRO 4.0.1 se generan los archivos `.abro` de atajados con
balance funcional. El flujo completo, con todas las reglas aprendidas
(decimales, sellos, validaciones), está documentado en **[AGENTS.md](AGENTS.md)**:

1. Se parte del archivo origen funcional (`duraznera`) con edición por texto puro.
2. Se sella con las clases Java reales del programa (`jjs` + `abro_app.jar`).
3. Se verifica `codigoControl` + `version` → OK/OK.
4. En ABRO se corre la cadena **ETo → Calcular, Demanda → Calcular, Balance → Calcular**.

Atajados generados con este flujo (archivos locales, fuera del repo):

| Atajado | Comunidad | Área | Oferta anual |
|---|---|---|---|
| La Abra (duraznera) | EL ABRA | 14.05 ha | 5 679.85 m³ |
| Tembladerayuc | UTURUNGO | 4.60 ha | 3 814.57 m³ |
| Keñuamayu | KEÑUAMAYU | 0.52 ha | 2 900.43 m³ |
| Charcomayu | YURAC CABALLO | 8.46 ha | 3 814.57 m³ |
| El Kenko | YURAC CABALLO | 7.71 ha | 2 581.47 m³ |

## Notas

- `abro.db` original nunca se copia: las lecturas usan `mode=ro` para no bloquear a Abro.exe.
- Escritura directa solo a tablas de referencia (suelos, cultivos, etc.). Los casos de
  estudio van a `./proyectos/*.json`, no al .db (ABRO no guarda proyectos en el .db).
- Los `.abro` de atajados **no se suben al repo** (datos de proyecto, repo público).
- Fórmulas según Manual Técnico ABRO 4.0.1 / FAO-56.
