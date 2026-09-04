"""Logos de empresa.

Orden de preferencia, de mas fiable a menos:

1. El logo que LinkedIn sirve en la propia tarjeta de la oferta. Es el mejor:
   viene de la misma fuente que el resto del dato y corresponde con seguridad a
   la empresa que publica.
2. El favicon del dominio de la empresa, cuando conocemos el dominio.
3. Nada: la ficha cae a un monograma con las iniciales.

Nunca se adivina un dominio para sacar un logo. Un logo equivocado en una ficha
comercial es peor que no tener logo: hace dudar del resto de la ficha.
"""

from __future__ import annotations

FAVICON = "https://icons.duckduckgo.com/ip3/{dominio}.ico"


def por_dominio(dominio: str | None) -> str | None:
    if not dominio:
        return None
    return FAVICON.format(dominio=dominio.strip().lower().lstrip("@"))
