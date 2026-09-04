# rrhh-tools — Radar de diseño junior

Busca en LinkedIn ofertas de **Junior Designer / Junior Product Designer / Junior UX-UI**
en España (Madrid o remoto) y las convierte en algo distinto de un listado de empleo:
una **lista de empresas a las que 2894 puede llamar** para presentarles perfiles.

Ese cambio de enfoque es lo que define el proyecto. La pieza central no es el scraper,
es el clasificador que separa clientes finales de agencias, consultoras e intermediarios.

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

### Antes de la primera búsqueda: resolver el geoId de Madrid

`config/config.yaml` trae el geoId de España ya verificado (`105646813`), pero el de la
Comunidad de Madrid viene como `PLACEHOLDER_GEOID_MADRID`. **La herramienta se niega a
lanzar una búsqueda con un geoId sin resolver**, a propósito: uno adivinado buscaría en
otra región sin dar ningún error y el informe saldría en silencio equivocado.

Para resolverlo: entra en LinkedIn, busca ofertas filtrando por Madrid, y copia el valor
del parámetro `geoId=` de la barra de direcciones a `config/config.yaml`.

Mientras tanto las búsquedas de ámbito España sí funcionan.

## Uso

```bash
uv run rrhh-tools search --source session --max-jobs 25 --record   # tirada corta primero
uv run rrhh-tools process --run latest                             # ver el reparto
uv run rrhh-tools report  --run latest                             # generar el informe
uv run rrhh-tools review  --run latest                             # cola de revisión
uv run rrhh-tools explain --company bankinter                      # desglose de una empresa
uv run rrhh-tools replay                                           # end-to-end sin red
```

`search` es el **único** comando que abre una conexión. El resto trabaja sobre lo ya
guardado en `data/`, así que puedes iterar sobre el análisis sin volver a pedirle nada
a LinkedIn.

Empieza siempre con `--max-jobs 25` para confirmar que la sesión funciona antes de
lanzar una ejecución completa.

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
uv run pytest        # 165 tests, todos sin red
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
