"""Clasificacion de la ubicacion de una oferta.

Madrid pesa mas que remoto-Espana, y remoto-Espana mas que el resto del pais,
porque los perfiles de 2894 estan en Madrid. Una oferta fuera de Espana no
sirve y puntua 0 en este factor.
"""

from __future__ import annotations

from ..models import LocationBucket
from ..normalize import basic_norm

_REMOTE_MARKERS = ("en remoto", "remoto", "remote", "teletrabajo", "desde casa", "anywhere")


def classify_location(
    location_raw: str,
    workplace_type: str | None,
    madrid_municipios: list[str],
    spain_markers: list[str],
) -> LocationBucket:
    text = basic_norm(location_raw)
    if not text and not workplace_type:
        return LocationBucket.UNKNOWN

    is_remote = (workplace_type or "").lower() == "remote" or any(
        marker in text for marker in _REMOTE_MARKERS
    )
    in_madrid = any(municipio in text for municipio in madrid_municipios)
    in_spain = in_madrid or any(marker in text for marker in spain_markers)

    # Madrid gana incluso si la oferta es remota: el equipo esta alli y una
    # empresa con sede en Madrid es mas facil de visitar para una reunion.
    if in_madrid:
        return LocationBucket.MADRID
    if is_remote and (in_spain or not text):
        return LocationBucket.REMOTE_ES
    if in_spain:
        return LocationBucket.REST_ES
    if text:
        return LocationBucket.OUTSIDE_ES
    return LocationBucket.UNKNOWN
