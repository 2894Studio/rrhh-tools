# rrhh-tools — Radar de diseño

Busca en LinkedIn **todas** las ofertas de diseño de producto, UX, UI y diseño con IA en
España (Madrid o remoto), de cualquier nivel, y las convierte en algo distinto de un
listado de empleo: una **lista de empresas a las que 2894 puede llamar** para presentarles
perfiles.

El nivel es un **filtro**, no una condición de entrada: se recoge la foto completa del
mercado y el informe deja quedarse con las junior en un clic.

Ese cambio de enfoque es lo que define el proyecto. La pieza central no es el scraper,
es el clasificador que separa clientes finales de agencias, consultoras e intermediarios.

## Nivel y rol

Cada oferta se etiqueta con su **nivel** (junior · mid · senior · lead) y su **rol**
(diseño con IA · producto · UX/UI · UX · UI · otro). Lo único que se descarta es lo que no
es diseño digital: diseño industrial, textil, de interiores.

El rol de **IA gana sobre los demás**: un *AI Product Designer* se etiqueta como IA, con
producto como secundario. Es el diferencial de los perfiles de 2894 y hay que poder
aislarlo de un vistazo.

El informe se ordena por **la oferta publicada más reciente**. Para actuar sobre una
vacante, lo primero que importa es que siga abierta; la prioridad sigue visible en cada
ficha y a un clic en el selector de orden.

## Los cuatro bloques del informe

| Bloque | Qué contiene | Para qué sirve |
|---|---|---|
| **A. Cuentas objetivo** | Clientes finales: banca, retail, seguros, SaaS, producto | **El entregable.** A quién llamar |
| **B. Señal de competencia** | Agencias y estudios (Nateevo, Flat 101, The Cocktail…) | Termómetro de demanda: si la competencia contrata junior, hay mercado |
| **C. Intermediarios** | Consultoras IT y empresas de selección | Ocultan al cliente real, aunque a veces la oferta lo deja entrever |
| **D. Por revisar** | Clasificación ambigua | Decisión humana. Aquí están las oportunidades que el sistema no supo resolver |

Las agencias **no se descartan**: se leen distinto. Que The Cocktail busque un becario
de UX es información de mercado, no ruido.

## Puesta en marcha

```bash
uv sync                          # instala dependencias
uv run playwright install chromium   # solo si vas a usar --source session
cp .env.example .env             # y pega ahí tu cookie li_at
```

### Antes de la primera búsqueda

```bash
uv run rrhh-tools doctor --source session
```

Comprueba la cookie, los geoId, que Chromium arranca y que los pesos cuadran, **sin tocar
LinkedIn**. El fallo más caro es descubrir a mitad de una tirada que faltaba la cookie.

Los dos geoId vienen resueltos: `105646813` para España y `100994331` para la Comunidad
de Madrid, ambos tomados de URLs públicas de LinkedIn. **Verificadlos en la primera
tirada**: filtrad por esa ubicación en LinkedIn y comparad el parámetro `geoId=` de la
barra de direcciones. Uno equivocado busca en otra región sin dar ningún error, y por eso
la herramienta se niega a lanzar una búsqueda cuyo geoId siga sin resolver.

## Uso

```bash
uv run rrhh-tools doctor  --source session                         # comprobaciones previas
uv run rrhh-tools search --source session --max-jobs 25 --record   # tirada corta primero
uv run rrhh-tools process --run latest                             # ver el reparto
uv run rrhh-tools report  --run latest                             # generar el informe
uv run rrhh-tools review  --run latest                             # cola de revisión
uv run rrhh-tools explain --company bankinter                      # desglose de una empresa
uv run rrhh-tools replay                                           # end-to-end sin red
uv run rrhh-tools curated                                          # lista curada inicial
uv run rrhh-tools site --publico                                   # versión para compartir
```

`search` es el **único** comando que abre una conexión. El resto trabaja sobre lo ya
guardado en `data/`, así que puedes iterar sobre el análisis sin volver a pedirle nada
a LinkedIn.

Empieza siempre con `--max-jobs 25` para confirmar que la sesión funciona antes de
lanzar una ejecución completa.

## Los dos modos de lectura de LinkedIn

| | `--source session` (por defecto) | `--source guest` |
|---|---|---|
| Login | Sí, con vuestra cookie `li_at` | No |
| Parser | `parsing/session.py` | `parsing/guest.py` |
| Descripción de la oferta | Sí, visitando cada `/jobs/view/<id>` | Sí, vía el endpoint público |
| Niveles que trae | Todos: el nivel lo decide el clasificador | Todos |
| Riesgo para la cuenta | LinkedIn puede restringirla | Ninguno |

**El DOM del LinkedIn con login no se parece al del público**: usa `job-card-container`
con `data-job-id` donde el público usa `base-card` con `data-entity-urn`. Por eso hay dos
parsers y no uno. Reutilizar los selectores públicos contra el DOM con sesión devuelve
cero ofertas —o, peor, datos basura que aparentan funcionar—; hay un test que lo fija.

El modo sesión **descarga la descripción de cada oferta** visitando su página. Cuesta una
petición más por oferta, pero de la descripción salen las señales más fuertes del
clasificador: las frases de intermediario (*"para uno de nuestros clientes"*), las
menciones de IA y la señal de *"serás el primer diseñador"*. Con `--no-details` se
salta ese paso: va más rápido y clasifica bastante peor.

## Sobre la cuenta de LinkedIn

`--source session` automatiza LinkedIn con tu cookie de sesión. Da más datos que el
endpoint público, pero conviene saberlo: **LinkedIn puede restringir o bloquear la cuenta
que se automatice**. Recomendación: usad una cuenta secundaria, no la principal de la
empresa.

Si la sesión queda restringida, `--source guest` usa el endpoint público sin login como
plan B.

Mitigaciones incluidas: ritmo fijo de 4 segundos entre peticiones, tope de 250 ofertas
por ejecución, parada limpia con checkpoint ante cualquier señal de límite, y abandono
inmediato si aparece el muro de login (reintentar no resucita una cookie caducada).

**No hay ni habrá evasión de detección**: nada de rotación de proxies, resolución de
CAPTCHAs ni falsificación de huella de navegador. Se recogen datos de empresa y de
oferta, nunca nombres ni perfiles de personas.

## La lista curada inicial

`rrhh-tools curated` renderiza `config/curated_targets.yaml`: una primera lista de
empresas a las que llamar, para no esperar a la primera ejecución del radar.

**No sale de LinkedIn.** Se construyó con búsqueda web y conocimiento del mercado
español, así que cada empresa lleva su nivel de evidencia: *vacante confirmada* o
*objetivo estratégico a verificar*. No se ha inventado ninguna oferta ni ninguna URL, y
donde la fuente anonimiza el nombre de la empresa se dice así en vez de adivinarlo.

Es un fichero YAML editable, para que el equipo comercial la mantenga a mano.

Cada empresa lleva un **enlace de búsqueda en LinkedIn** para comprobar sus vacantes en el
momento. Son búsquedas, no URLs de ofertas: una URL de oferta que no hemos visto sería
inventada y podría llevar a una vacante que ya no existe; una búsqueda siempre refleja el
estado real de LinkedIn en el instante del clic.

## La versión pública

`--publico` genera una variante del sitio **sin el razonamiento comercial**: quedan las
empresas, sus datos, los logos y los enlaces a LinkedIn, y desaparece por qué son objetivo,
cuál es el siguiente paso y cualquier orden de prioridad.

Existe porque el sitio desplegado está en internet abierto. Con la variante pública el
enlace se puede compartir aunque nunca se active la protección de acceso de Vercel.

El recorte se hace en el renderer con una **lista de campos permitidos**, no con
condicionales en la plantilla. Es deliberado: si mañana se añade un campo al YAML, queda
fuera de lo público por omisión en vez de colarse porque nadie actualizó una lista de
exclusiones. Hay un test que lo comprueba con un campo inventado.

La muestra del radar del sitio usa **empresas ficticias**. Publicar que una empresa real
"no es cliente final", o puntuarla con un 92 bajo la marca de 2894 y en abierto, no procede.

## Cómo mejorar el clasificador

El sistema aprende de vosotros. `rrhh-tools review` imprime los casos dudosos ya en el
formato de `config/decisions.yaml`, listos para pegar. Ese fichero **se commitea**: es
conocimiento acumulado del equipo, y las decisiones manuales mandan sobre cualquier
otra regla.

Si el clasificador se equivoca con una empresa concreta:
- La marca como intermediario y no lo es → añádela a `config/allowlist.yaml`.
- La da por buena y es una agencia → añádela a `config/denylist.yaml`.

Los pesos del scoring están en `config/config.yaml` y deben sumar 100; la herramienta lo
valida al arrancar.

## Desarrollo

```bash
uv run pytest        # 274 tests, todos sin red
```

Un guardia en `tests/conftest.py` hace **fallar** cualquier test que intente abrir una
conexión. Así la suite funciona sin conectividad y ningún test empieza a depender en
silencio de que LinkedIn esté disponible.

### Una limitación que conviene conocer

Los selectores HTML están escritos a partir de la estructura conocida del LinkedIn
público, pero **no se han podido verificar contra el sitio real**: el entorno donde se
construyó el proyecto no tenía salida a internet. Los fixtures de `tests/fixtures/http/`
son reproducciones a mano, no capturas.

Sirven para fijar el contrato del parser y detectar regresiones, pero no garantizan que
los selectores casen con el LinkedIn de hoy. Por eso los parsers son multi-selector y
anotan avisos en vez de romperse, y por eso existe `--record`: guarda el HTML real
recibido para poder ajustar los selectores en un ciclo.

**Ese primer ciclo de ajuste es trabajo previsto, no un fallo.**

## Diseño del informe

El informe sigue la guía de marca de 2894: DM Sans como única familia, jerarquía por peso
y escala, lienzo cloud-white y un solo bloque cobalto sólido (el panel de temperatura de
mercado), según la regla de un único elemento destacado por rejilla.

Dos restricciones de la paleta obligaron a decisiones concretas:

- La marca prohíbe los tonos cálidos, así que **la prioridad no usa el semáforo
  rojo/ámbar/verde**: se codifica con intensidad de cobalto.
- `sky-blue` sobre `cloud-white` da **1.96:1** de contraste, muy por debajo del mínimo AA
  de 4.5. Solo se usa como elemento gráfico, o como texto sobre `ink-black`, donde llega
  a 9.45:1.

## Qué no hace

- No envía correos ni mensajes. Prepara la lista; la conversación la tenéis vosotros.
- No afirma ser exhaustivo. Recoge lo que se vio en las búsquedas configuradas, no todas
  las ofertas de diseño junior que existen en España.
- No inventa fechas exactas. Cuando LinkedIn solo da "hace 2 semanas", el informe lo
  trata como el rango que es y pondera la frescura por esa incertidumbre.
