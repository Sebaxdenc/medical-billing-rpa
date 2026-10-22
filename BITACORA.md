# Bitácora

## 1. Herramienta de IA

Usé ChatGPT/Copilot SDK integrado en VS Code como asistente de análisis,
diseño, implementación y revisión.

Lo utilicé para:

- proponer una estructura pequeña para el proyecto;
- discutir la diferencia entre errores de negocio y errores técnicos;
- implementar el cliente HTTP, el almacenamiento en SQLite, el reporte Excel,
  el logging y la CLI;
- sugerir pruebas automatizadas para reintentos e idempotencia;
- revisar una decisión de validación que luego corregí;
- ejecutar y analizar las pruebas y una ejecución real con el CSV entregado.

La responsabilidad de revisar el código, entenderlo y decidir el
comportamiento final fue mía.

## 2. Prompts útiles

Estos fueron algunos prompts que utilicé literalmente:

> Para este proyecto no quiero q hagas nada por tu cuenta, primero explicame
> que planeas para que yo lo apruebe, la idea es que el proyecto sea mio.

Me sirvió para establecer primero la arquitectura y las decisiones de negocio,
en vez de aceptar una implementación que no pudiera explicar.

> porque el 0 se asume como invalid input? podria considerarse perfectamente un
> input valido? o es algun estandar que yo no se?

Este prompt detectó una suposición no justificada en la validación de IDs y
abrió la discusión sobre la diferencia entre una regla del negocio y una
limitación de la API.

> podriamos probar esto? : . El proceso tiene que ser re-ejecutable: si lo
> corres dos veces seguidas, la segunda no vuelve a consultar lo que ya
> resolvió ni duplica filas en el Excel. Si se cae a la mitad, al relanzarlo
> retoma donde quedó.

Lo usé para revisar cómo demostrar la idempotencia, la reanudación y el
comportamiento de los reintentos, en lugar de dar esas propiedades por
supuestas.

> me gustaria revisar esto: el resultado de 429 y el 408 de https. El README
> manda todo "otro 4xx" a `BUSINESS_ERROR` sin reintento. Pero 429 (demasiadas
> solicitudes) y 408 (timeout) son transitorios y sí tiene sentido
> reintentarlos.

Este prompt sirvió para revisar la frontera de reintentos con más detalle y no
tratar todos los códigos `4xx` como si tuvieran la misma causa o acción
operativa.

## 3. Algo que la IA entregó mal o incompleto

La primera implementación trató `0` como `INVALID_INPUT` mediante esta regla:

```python
if not raw_id.isdigit() or int(raw_id) < 1:
```

La IA justificó inicialmente esa decisión suponiendo que un ID técnico debía
ser mayor que cero. Esa suposición no estaba en el enunciado. Un número de
cuenta podría ser `0` si el sistema de origen lo permite, y no hay un estándar
universal que prohíba el cero en un identificador.

Lo detecté revisando el caso incluido en `cuentas.csv` y preguntando
explícitamente por qué se descartaba. Decidí aceptar enteros no negativos:
`0, 1, 2, ...`. De esa forma, `0` se consulta contra la API y la API decide
si el recurso existe. Si responde `404`, el resultado es
`BUSINESS_NOT_FOUND`, no `INVALID_INPUT`.

También revisé la forma de ejecutar el comando de limpieza de SQLite. El
primer comando tenía un problema de comillas en PowerShell, por lo que no
llegó a ejecutarse. Se corrigió usando un bloque de código enviado por pipe a
Python. Esto confirmó que los comandos operativos también deben probarse en el
entorno real de ejecución y no solo escribirse como texto.

Después revisé otra simplificación inicial: documentar todos los códigos
`4xx` como `BUSINESS_ERROR` sin reintentos. Eso era demasiado general. Aunque
todos pertenecen a la familia de errores del lado de la solicitud, no todos
representan el mismo problema:

- `404` indica que el recurso no existe y se mantiene como
  `BUSINESS_NOT_FOUND`.
- `408` puede ser transitorio y se reintenta.
- `429` indica limitación de tráfico y se reintenta respetando `Retry-After`
  cuando está disponible.
- `401` y `403` normalmente indican credenciales, permisos o configuración,
  por lo que se clasifican como `CONFIGURATION_ERROR` y no se reintentan.
- Otros `4xx` funcionales se mantienen como `BUSINESS_ERROR` sin reintento.

La corrección se verificó agregando pruebas para `408`, `429` con
`Retry-After` y `401`, además de actualizar el README para que la
documentación y el comportamiento real coincidieran.

## 4. Decisiones propias

### Deduplicar los IDs

Decidí generar una sola fila por ID normalizado, aunque aparezca varias veces
en el CSV. El resultado de la consulta depende del identificador y no de la
cantidad de veces que aparezca en el archivo. Esta decisión evita llamadas
innecesarias, evita filas duplicadas y hace que una segunda ejecución sea
naturalmente idempotente. La decisión queda documentada porque otra opción
válida habría sido conservar cada ocurrencia del archivo.

### Conservar entradas inválidas como resultados auditables

Los valores vacíos o no numéricos no se envían a la API, pero tampoco se
descartan silenciosamente. Se registran como `INVALID_INPUT`, con una
explicación en el estado y en el Excel. En un proceso nocturno de facturación
es importante poder demostrar qué llegó en el CSV y por qué no se consultó,
en lugar de que el total de entrada y el total reportado no coincidan sin
explicación.

### Aceptar `0` como entero válido

Decidí aceptar todos los enteros no negativos, incluido `0`, porque el
enunciado no define que las cuentas deban comenzar en `1`. La validación no
debe inventar una regla de negocio. Si `0` no existe en el sistema externo,
la respuesta correcta es un `404` y se clasifica como
`BUSINESS_NOT_FOUND`. Los números negativos, los textos y los valores vacíos
sí se mantienen como entradas inválidas porque no cumplen el formato elegido
para este reto.

### Separar errores de negocio de errores técnicos

Un `404` significa que la API respondió correctamente que no existe el
recurso; por eso se marca como `BUSINESS_NOT_FOUND` y no se reintenta. En
cambio, un timeout, un error de conexión, un `408`, un `429` o un `5xx` no
permite saber si el recurso existe o indican una condición temporal del
servicio. Esos casos se clasifican como técnicos y se reintentan. Esta
frontera evita perder tiempo repitiendo una respuesta funcional que no
cambiará y permite recuperar fallos transitorios.

También decidí no agrupar automáticamente `401` y `403` como errores de
negocio. Aunque son códigos `4xx`, en una ejecución RPA suelen indicar una
credencial vencida, un token incorrecto, permisos insuficientes o una
configuración de ambiente incompleta. Por eso se usa el estado
`CONFIGURATION_ERROR`, que es más accionable para el runbook y no se reintenta
hasta corregir la causa.

Los códigos `400`, `409`, `422` y otros `4xx` funcionales se mantienen como
`BUSINESS_ERROR`. Esta categoría se reserva para solicitudes rechazadas por
reglas funcionales o datos no válidos, donde repetir exactamente la misma
solicitud no cambiaría la respuesta.

Para `429`, además, se respeta el header `Retry-After` de la API. Si no está
presente o no se puede interpretar, se aplica el backoff exponencial
configurado. Así el cliente coopera con el límite de tráfico del servicio en
lugar de reintentar de forma agresiva.

### Usar SQLite como fuente de verdad

Elegí SQLite en vez de usar el Excel como mecanismo de control. SQLite permite
guardar el resultado de cada ID en una transacción independiente. Si el
proceso se interrumpe, los IDs ya terminados quedan persistidos y se pueden
omitir al relanzar. Además, una clave primaria sobre `account_id` impide
duplicados. El Excel se considera un reporte reconstruible, no el estado
operativo principal.

### Reconstruir el Excel desde el estado persistido

Decidí generar el Excel a partir de SQLite en cada ejecución. Así el archivo
queda consistente con la fuente de verdad y no depende de anexar filas
manualmente. Esto también evita duplicar resultados cuando se ejecuta el
proceso dos veces.

### Usar reintentos limitados con backoff exponencial

La configuración usa tres intentos totales y dos esperas entre ellos:
`1` segundo antes del segundo intento y `2` segundos antes del tercero, con
parámetros fuera del código. El límite evita que un endpoint caído bloquee
indefinidamente el proceso nocturno. El backoff reduce la presión sobre el
servicio externo y da tiempo para que se recupere. La secuencia `1`, `2`, `4`
y `8` solo aparecería si se configuraran cinco intentos totales.

### Procesar secuencialmente

Elegí procesamiento secuencial porque el reto prioriza trazabilidad,
reanudación y claridad sobre velocidad. El volumen entregado es pequeño y no
justifica introducir concurrencia, límites de tasa o problemas adicionales de
coordinación. Cada ID se guarda antes de pasar al siguiente.

### Configurar parámetros fuera del código

Usé `config.toml` para la URL, timeout, número de intentos, backoff y rutas de
salida. Esto permite cambiar valores operativos sin editar la lógica y hace
más claro qué parte es configuración de ambiente y qué parte es regla del
proceso.

### Separar el estado por lote diario

Decidí que la idempotencia debe aplicar al mismo lote, no al
`account_id` global. El proceso se ejecuta cada día con un CSV nuevo y el
sistema externo puede cambiar entre ejecuciones. Si la cuenta `7` se procesó
hoy, no sería correcto reutilizar automáticamente ese resultado mañana solo
porque el identificador es el mismo.

Por eso la clave del estado es `(batch_id, account_id)`. El `batch_id` combina
la fecha local y un hash corto del contenido del CSV. Esto permite relanzar el
mismo archivo el mismo día sin repetir llamadas terminales, pero crea un lote
nuevo al día siguiente o cuando cambia el contenido del archivo. El Excel se
filtra por el lote actual y contiene únicamente las cuentas del CSV actual,
mientras SQLite conserva el histórico de lotes para auditoría.

Esta decisión evita dos errores opuestos: repetir llamadas dentro del mismo
lote y, al mismo tiempo, usar datos viejos de un día anterior. También deja
explícito en el runbook que no se debe borrar SQLite al relanzar, porque allí
están tanto el punto de reanudación como el histórico.
