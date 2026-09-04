from pathlib import Path

import pytest

from rrhh_tools.http import AuthWall, FixtureFetcher, ThrottleStop, _is_authwall, url_key


def test_el_fixture_fetcher_sustituye_al_cliente_real(fixtures_dir):
    f = FixtureFetcher(fixtures_dir)
    assert hasattr(f, "get")
    with pytest.raises(FileNotFoundError, match="No hay fixture"):
        f.get("https://www.linkedin.com/inexistente")


def test_se_detecta_el_muro_de_login():
    assert _is_authwall("https://www.linkedin.com/authwall?x=1", "")
    assert _is_authwall("https://www.linkedin.com/uas/login", "")
    assert _is_authwall("https://www.linkedin.com/checkpoint/challenge", "")
    assert _is_authwall("https://www.linkedin.com/jobs/view/1", "<html>Sign in to continue</html>")
    assert not _is_authwall("https://www.linkedin.com/jobs/view/1", "<html>Junior UX</html>")


def test_la_clave_de_url_es_estable():
    a = url_key("https://www.linkedin.com/x")
    assert a == url_key("https://www.linkedin.com/x")
    assert a != url_key("https://www.linkedin.com/y")


def test_la_sesion_sin_cookie_falla_con_mensaje_util(monkeypatch):
    monkeypatch.delenv("LINKEDIN_LI_AT", raising=False)
    from rrhh_tools.sources.session import _cookie
    with pytest.raises(AuthWall, match="LINKEDIN_LI_AT"):
        _cookie()
