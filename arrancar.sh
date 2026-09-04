#!/usr/bin/env bash
# Primera tirada real contra LinkedIn, en un solo comando.
#
#   ./arrancar.sh
#
# Empieza por el modo `guest`, que NO necesita cookie ni navegador: es el
# endpoint publico de ofertas de LinkedIn. Si LinkedIn responde con el muro de
# login -pasa a veces-, el script te explica como pasar al modo `session`, que
# si necesita cookie.
#
# Ventana de 7 dias en la primera tirada. La config trae 24h porque esta
# pensada para una tirada diaria, y en la primera ejecucion esa ventana deja
# casi todo fuera: parece que no encuentra nada cuando lo que pasa es que solo
# mira lo de hoy.

set -uo pipefail
cd "$(dirname "$0")"

DIAS=${DIAS:-7}
MAX=${MAX:-40}
FUENTE=${FUENTE:-guest}

echo
echo "  Radar de diseño — primera tirada"
echo "  fuente: $FUENTE · ventana: $DIAS días · tope: $MAX ofertas"
echo

# --- 1. uv -------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  cat <<'AYUDA'
  Falta `uv`, que es lo unico que hace falta instalar. Un comando:

      curl -LsSf https://astral.sh/uv/install.sh | sh

  (en Windows, desde PowerShell:
      powershell -c "irm https://astral.sh/uv/install.ps1 | iex")

  Cierra y reabre la terminal, y vuelve a lanzar ./arrancar.sh
AYUDA
  exit 1
fi

echo "→ Instalando dependencias…"
uv sync --quiet || { echo "  Fallo en 'uv sync'. Pega la salida y lo miramos."; exit 1; }

# --- 2. Comprobaciones previas, sin tocar LinkedIn --------------------------
echo
echo "→ Comprobaciones previas"
uv run rrhh-tools doctor --source "$FUENTE" || exit 1

# --- 3. La tirada ------------------------------------------------------------
echo
echo "→ Buscando en LinkedIn. Con 4s entre peticiones, esto tarda unos minutos."
echo "  Se puede parar con Ctrl-C: lo descargado queda guardado y se reanuda"
echo "  con --resume."
echo
uv run rrhh-tools search --source "$FUENTE" --dias "$DIAS" --max-jobs "$MAX" --record
CODIGO=$?

case $CODIGO in
  0) ;;
  3)
    cat <<'AYUDA'

  LinkedIn ha devuelto el MURO DE LOGIN. El endpoint publico no siempre esta
  disponible; hay que ir con sesion iniciada. Son tres pasos:

    1. uv run playwright install chromium
    2. Abre linkedin.com con tu sesion. En el navegador:
         Chrome/Edge:  F12 → Application → Cookies → https://www.linkedin.com
         Firefox:      F12 → Almacenamiento → Cookies
       Copia el valor de la cookie `li_at` (una cadena larga).
    3. cp .env.example .env
       y pega el valor:   LINKEDIN_LI_AT=<lo que copiaste>

  Y relanza:   FUENTE=session ./arrancar.sh

  El fichero .env esta en .gitignore: la cookie no se sube a ningun sitio ni
  se imprime por pantalla.
AYUDA
    exit 3 ;;
  4)
    echo
    echo "  LinkedIn esta limitando las peticiones. Se ha guardado lo descargado."
    echo "  Reanuda mas tarde:  uv run rrhh-tools search --source $FUENTE --resume"
    exit 4 ;;
  5)
    echo
    echo "  No hay conexión con LinkedIn desde esta máquina. El mensaje de arriba"
    echo "  dice las causas típicas. Pruébalo en el navegador de este mismo equipo."
    exit 5 ;;
  *)
    echo
    echo "  La búsqueda ha fallado (código $CODIGO). Pega la salida y lo miramos."
    exit $CODIGO ;;
esac

# --- 4. El informe -----------------------------------------------------------
echo
echo "→ Generando el informe"
uv run rrhh-tools report --out reports/radar.html || exit 1

echo
echo "  Listo:  reports/radar.html"
echo
echo "  Si quieres el sitio entero (portada + empresas + radar):"
echo "      uv run rrhh-tools site --out site"
echo

# Abrirlo, si el sistema sabe como.
if   command -v open    >/dev/null 2>&1; then open reports/radar.html
elif command -v xdg-open >/dev/null 2>&1; then xdg-open reports/radar.html
fi
