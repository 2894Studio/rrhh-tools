from datetime import date

import pytest

from rrhh_tools.dates import days_since, parse_relative_date

HOY = date(2026, 9, 4)


@pytest.mark.parametrize("texto,dias_esperados,confianza", [
    ("hace 3 días", 3, 1.0),
    ("3 days ago", 3, 1.0),
    ("Reposted 3 days ago", 3, 1.0),
    ("hace 2 semanas", 18, 0.6),
    ("2 weeks ago", 18, 0.6),
    ("hace 1 mes", 45, 0.3),          # 'mes' no debe perder la 's' al singularizar
    ("hace 3 meses", 105, 0.3),
    ("hace 5 horas", 0, 1.0),
    ("justo ahora", 0, 1.0),
])
def test_fechas_relativas(texto, dias_esperados, confianza):
    fecha, conf = parse_relative_date(texto, HOY)
    assert days_since(fecha, HOY) == dias_esperados
    assert conf == confianza


@pytest.mark.parametrize("texto", [None, "", "texto sin fecha"])
def test_lo_no_reconocido_devuelve_confianza_neutra(texto):
    fecha, conf = parse_relative_date(texto, HOY)
    assert fecha is None
    assert conf == 0.5   # 0.5 es el valor neutro de frescura en el scoring


def test_days_since_devuelve_entero_para_hoy():
    # Un timedelta de cero es falsy: este caso detecta el bug clásico de
    # escribirlo con un 'and' que se cortocircuita.
    assert days_since(HOY, HOY) == 0
    assert isinstance(days_since(HOY, HOY), int)
