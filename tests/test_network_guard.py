"""El guardia de red debe morder de verdad."""

import pytest
import requests


def test_la_red_esta_bloqueada_en_los_tests():
    with pytest.raises(AssertionError, match="salir a la red"):
        requests.get("https://www.linkedin.com/")
