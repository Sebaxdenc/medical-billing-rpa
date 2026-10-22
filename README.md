# Medical Billing RPA

Proceso batch idempotente para leer `cuentas.csv`, consultar cada cuenta en
JSONPlaceholder y generar un Excel consolidado.

## Requisitos

- Python 3.11+
- Dependencias de `requirements.txt`

## Ejecución

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m rpa_billing --input cuentas.csv --config config.toml
```

La salida queda en `output/resultados.xlsx`, el estado durable en
`runtime/state.db` y el log en `logs/`. Las rutas, timeout y reintentos se
configuran en `config.toml`.

## Decisiones funcionales

- Los IDs se normalizan quitando espacios y comillas externas. Los repetidos
  se deduplican y producen una sola fila.
- Un ID vacío o no numérico se conserva como `INVALID_INPUT` y no genera una
  llamada HTTP. Se aceptan enteros no negativos, incluido `0`; si el recurso
  no existe, la API determina el resultado mediante `404`.
- Un 404 es `BUSINESS_NOT_FOUND` y no se reintenta. Los errores de red,
  timeout y respuestas 5xx son técnicos y se reintentan con backoff
  exponencial. Los demás 4xx son errores de negocio no reintentables.
- SQLite es la fuente de verdad. El Excel se reconstruye desde SQLite en
  cada ejecución; por eso no duplica filas ni repite llamadas exitosas.

## Runbook de madrugada

1. Revisar el resumen final y `logs/` para identificar estados por causa.
2. Si hubo errores técnicos, verificar conectividad y disponibilidad de la API
   y relanzar el mismo comando.
3. Validar que `output/resultados.xlsx` existe y contiene los IDs únicos del
   CSV.
4. No borrar `runtime/state.db` antes de relanzar: repetiría llamadas.

El proceso es secuencial para mantener el comportamiento simple y auditable.

## Limitaciones conocidas

La API de prueba puede cambiar o no estar disponible. No se agregan
notificaciones externas ni ejecución concurrente porque no son necesarias para
el alcance del reto.
