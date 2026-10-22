# Medical Billing RPA

Proceso batch para una operación RPA nocturna. Lee los números de cuenta desde
un CSV, consulta el recurso correspondiente en
`https://jsonplaceholder.typicode.com/posts/{id}` y genera un Excel consolidado
para auditoría.

El proceso está diseñado para ejecutarse sin supervisión:

- un ID que falla no detiene los demás;
- los resultados se guardan individualmente;
- las llamadas exitosas no se repiten al relanzar;
- el Excel contiene únicamente el lote/CSV actual y no acumula filas de días
  anteriores;
- cada ejecución deja log y resumen.

## Qué necesita instalado

- Python 3.11 o superior.
- Acceso de red al endpoint de JSONPlaceholder.
- Paquetes Python declarados en `requirements.txt`:
  - `requests`, para las consultas HTTP;
  - `openpyxl`, para generar el archivo Excel.

SQLite y `tomllib` forman parte de Python, por lo que no requieren un servicio
externo ni una dependencia adicional.

## Instalación

Desde la raíz del repositorio, en PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

La instalación editable permite ejecutar el paquete `rpa_billing` directamente
con `python -m`.

## Entrada y configuración

El archivo de entrada por defecto es `cuentas.csv` y debe tener una columna
llamada `id_cuenta`. El lector tolera espacios alrededor del valor, comillas
externas y líneas vacías.

La configuración operativa está fuera del código, en `config.toml`:

```toml
[api]
base_url = "https://jsonplaceholder.typicode.com/posts"
timeout_seconds = 10
max_attempts = 3
backoff_seconds = 1

[paths]
state_db = "runtime/state.db"
output_xlsx = "output/resultados.xlsx"
log_dir = "logs"
```

Se pueden cambiar la URL, timeout, cantidad de intentos, backoff y rutas sin
modificar la lógica del proceso.

## Cómo se ejecuta

Con la configuración y nombres por defecto:

```powershell
python -m rpa_billing --input cuentas.csv --config config.toml
```

También se pueden pasar otros archivos:

```powershell
python -m rpa_billing --input entradas\cuentas-2026-10-22.csv --config config.toml
```

Al terminar se generan:

- `output/resultados.xlsx`: reporte con una fila por ID único y las columnas
  `id_cuenta`, `estado`, `titulo`, `detalle`, `error` e `intentos`.
- `runtime/state.db`: estado durable del proceso; es la fuente de verdad para
  reanudar y conserva el histórico de lotes.
- `logs/run-YYYYMMDD-HHMMSS.log`: detalle de cada ID, omisiones y resumen.

## Decisiones funcionales

### IDs repetidos

Los valores se normalizan quitando espacios y comillas externas. Los
duplicados se deduplican y producen una sola fila y una sola consulta lógica.
La decisión representa que el resultado depende del identificador, no de
cuántas veces fue escrito en el CSV. También evita llamadas innecesarias y
filas duplicadas en el Excel.

### IDs inválidos y cero

Los valores vacíos o no numéricos se conservan como `INVALID_INPUT`, no se
envían a la API y quedan registrados para auditoría. No se descartan
silenciosamente.

Se aceptan todos los enteros no negativos, incluido `0`. El programa no
inventa una regla que obligue a que una cuenta comience en `1`. Si `0` o
cualquier otro entero no existe en el sistema externo, la respuesta funcional
la determina la API mediante `404`.

Los valores negativos no cumplen el formato elegido para este reto y quedan
como `INVALID_INPUT`.

### Estados y frontera de reintentos

| Situación | Estado | Reintenta |
|---|---|---:|
| Respuesta correcta con datos | `SUCCESS` | No |
| API responde `404` | `BUSINESS_NOT_FOUND` | No |
| `400`, `409`, `422` u otro `4xx` funcional | `BUSINESS_ERROR` | No |
| `401` o `403` | `CONFIGURATION_ERROR` | No |
| `408 Request Timeout` | `TECHNICAL_FAILED` | Sí |
| `429 Too Many Requests` | `TECHNICAL_FAILED` | Sí |
| Timeout o error de conexión | `TECHNICAL_FAILED` | Sí |
| Respuesta `5xx` | `TECHNICAL_FAILED` | Sí |
| Respuesta exitosa con JSON inválido | `TECHNICAL_FAILED` | Sí |
| Entrada vacía/no numérica/negativa | `INVALID_INPUT` | No |

Todas las respuestas HTTP `4xx` son errores del lado de la solicitud, pero no
todas tienen la misma acción operativa. Un `404` es un resultado de negocio:
la API respondió correctamente que el recurso no existe. Los demás errores
funcionales como `400`, `409` o `422` se agrupan como `BUSINESS_ERROR`.

Un `401` o `403` se informa como `CONFIGURATION_ERROR`, porque normalmente
indica credenciales, permisos o configuración incorrecta. No se reintenta
automáticamente: repetir la misma solicitud no corrige esas condiciones y
podría ocultar un problema de despliegue.

Un `408` puede ser transitorio porque el servidor no completó la solicitud a
tiempo. Un `429` indica limitación de tráfico, por lo que también puede ser
transitorio. Ambos se reintentan. Para `429`, si la respuesta contiene el
header `Retry-After`, se respeta su valor; si no existe o no se puede
interpretar, se usa el backoff exponencial configurado. Ante timeout de
cliente, error de conexión o `5xx` tampoco se puede concluir si el recurso
existe, por lo que sí tiene sentido reintentar.

La política por defecto es de tres intentos totales, con dos esperas entre
ellos: 1 segundo antes del segundo intento y 2 segundos antes del tercero.
La cantidad de intentos y el tiempo inicial son configurables. Si se agotaran
cinco intentos, las esperas serían 1, 2, 4 y 8 segundos.

### Idempotencia y reanudación

SQLite guarda cada resultado con la clave compuesta `(batch_id, account_id)`.
El lote se calcula como `YYYY-MM-DD-<hash corto del contenido del CSV>`.
Después de resolver cada ID, el resultado se confirma en una transacción
independiente. Al relanzar el mismo archivo el mismo día:

- los estados terminales (`SUCCESS`, `BUSINESS_NOT_FOUND`, `BUSINESS_ERROR`,
  `CONFIGURATION_ERROR` e `INVALID_INPUT`) se omiten;
- un `TECHNICAL_FAILED` vuelve a intentarse, porque pudo ser transitorio;
- los IDs procesados antes de una interrupción no vuelven a llamar a la API;
- el Excel se reconstruye desde SQLite filtrando el lote actual.

El alcance del estado es el lote, no el `account_id` global. Si mañana llega
otra vez la cuenta `7`, tendrá un lote distinto y se consultará nuevamente,
porque el sistema externo pudo haber cambiado. SQLite conserva ambos
resultados para auditoría, pero el Excel de mañana contiene solo los IDs del
CSV de mañana.

El hash hace que relanzar exactamente el mismo archivo el mismo día use el
mismo lote. La fecha evita reutilizar el resultado de un día anterior aunque
el contenido del CSV sea idéntico. El formato también permite procesar dos
archivos con contenidos diferentes el mismo día sin mezclarlos.

Si se ejecuta un CSV nuevo con un lote diferente, el Excel se sobrescribe con
el reporte de ese lote; no es un reporte histórico acumulado.

Si la interrupción ocurre durante una llamada, ese ID puede volver a
intentarse al relanzar. Es intencional: todavía no existía un resultado
confirmado que guardar.

El proceso es secuencial para mantener trazabilidad y simplificar la
reanudación. Cada ID se guarda antes de continuar con el siguiente.

## Runbook: falla a las 3:00 a.m.

### 1. Confirmar qué ocurrió

Ubicar el log más reciente:

```powershell
Get-ChildItem logs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```

Abrirlo y buscar el `Resumen final`. Si no existe, el proceso probablemente
fue interrumpido antes de terminar. Revisar también los últimos registros del
log para identificar el último ID tratado.

### 2. Revisar los estados

Interpretar el resumen así:

- `SUCCESS`: consulta resuelta correctamente.
- `BUSINESS_NOT_FOUND`: el ID fue consultado, pero no existe en el sistema
  externo; no es una falla de infraestructura.
- `BUSINESS_ERROR`: la API respondió un error funcional `4xx`, como `400`,
  `409` o `422`.
- `CONFIGURATION_ERROR`: la API rechazó la autenticación o autorización con
  `401` o `403`; revisar credenciales, permisos o configuración.
- `INVALID_INPUT`: el CSV contiene un valor que no cumple el formato.
- `TECHNICAL_FAILED`: la API no pudo responder después de los reintentos.

### 3. Si hay errores técnicos, revisar conectividad

Desde el mismo equipo donde corre el proceso:

```powershell
Invoke-WebRequest `
  -Uri "https://jsonplaceholder.typicode.com/posts/1" `
  -TimeoutSec 10
```

Si falla la conectividad, informar la indisponibilidad y relanzar cuando se
recupere. Si responde correctamente, continuar con el relanzamiento del
proceso.

### 4. Relanzar sin borrar el estado

Ejecutar exactamente el mismo comando:

```powershell
python -m rpa_billing --input cuentas.csv --config config.toml
```

No borrar `runtime/state.db`: contiene los resultados ya confirmados de todos
los lotes y permite reanudar sin repetir llamadas exitosas del lote actual.
Tampoco es necesario borrar el Excel; se reconstruirá al final con el lote
actual.

### 5. Validar la entrega

Confirmar que existen:

```powershell
Test-Path output\resultados.xlsx
Test-Path runtime\state.db
```

Revisar el nuevo resumen y comprobar que el Excel contiene una fila por cada
ID único normalizado del CSV. Los `BUSINESS_NOT_FOUND` e `INVALID_INPUT` deben
quedar visibles y no deben confundirse con una caída del proceso.

Si el proceso falla nuevamente, conservar los logs de ambas ejecuciones,
reportar el último estado observado y no eliminar la base de estado. Eso
permite continuar el diagnóstico sin perder trazabilidad.

## Limitaciones conocidas

- JSONPlaceholder es un servicio de prueba; en producción se reemplazaría
  `base_url` por el endpoint real y se revisarían sus códigos de respuesta.
- No se implementan notificaciones externas ni ejecución concurrente. Para el
  volumen del reto se priorizaron trazabilidad, simplicidad y reanudación.
- La salida se genera al final de la ejecución. La persistencia intermedia está
  en SQLite, por lo que los resultados ya confirmados se conservan aunque el
  proceso se interrumpa antes de escribir el Excel.
- El lote se identifica con la fecha local del equipo y un hash del archivo.
  Si el negocio dispone de un identificador oficial de lote, podría sustituir
  esta convención en una evolución posterior.
