"""Forma de los enlaces publicados.

ESTE FICHERO ES EL QUE FALTABA
------------------------------
Los enlaces salieron rotos a produccion porque no habia ni un solo test sobre
ellos. El bug era este:

    keywords = "Cabify designer OR diseñador OR UX OR UI"

el nombre de la empresa metido como texto libre en una cadena de OR, sin la
faceta de empresa (f_C) que es lo unico que acota una busqueda a una compania.
La restriccion se perdia y la busqueda devolvia un listado general o nada.

No se puede comprobar desde aqui si una URL vive: la red esta bloqueada, y de
todas formas una oferta puede morir manana. Lo que si se puede fijar, y es lo
que hacen estos tests, es que la FORMA de cada URL sea correcta por
construccion. Lo otro lo comprueba `rrhh-tools links --check` con red.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

from rrhh_tools import linkedin_links
from rrhh_tools.linkedin_links import SLUG, company_jobs, jobs_by_name, jobs_by_role
from rrhh_tools.report.render import render_curated

RUTA_YAML = Path("config/curated_targets.yaml")


@pytest.fixture(scope="module")
def datos() -> dict:
    return yaml.safe_load(RUTA_YAML.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def html(datos) -> str:
    return render_curated(datos, "t", geo_id="100994331", geo_es="105646813")


def _hrefs(texto: str) -> list[str]:
    import html as h
    return [h.unescape(u) for u in re.findall(r'href="([^"]+)"', texto)]


# --------------------------------------------------------------------------
# El bug concreto, con candado

def test_el_constructor_que_rompia_los_enlaces_ya_no_existe():
    """`job_search` pegaba la empresa a una cadena de OR. No debe volver.

    Se comprueba el modulo, no una llamada: si alguien lo reintroduce con la
    misma firma, este test lo ve aunque nadie lo llame todavia.
    """
    assert not hasattr(linkedin_links, "job_search")
    assert not hasattr(linkedin_links, "DESIGN_TERMS")


def test_ninguna_busqueda_lleva_una_cadena_de_or(html):
    for url in _hrefs(html):
        for valor in parse_qs(urlparse(url).query).get("keywords", []):
            assert " OR " not in valor, f"vuelve la cadena de OR en {url}"


def test_la_busqueda_por_nombre_lleva_solo_el_nombre():
    url = jobs_by_name("Cabify", "100994331")
    assert parse_qs(urlparse(url).query)["keywords"] == ["Cabify"]
    assert parse_qs(urlparse(url).query)["geoId"] == ["100994331"]


# --------------------------------------------------------------------------
# Slugs

@pytest.mark.parametrize("malo", ["", "  ", "-cabify", "cabify-", "a/b", "Clarity AI", "a_b"])
def test_un_slug_invalido_no_construye_url(malo):
    """Devolver None es deliberado: quien llama cae en la busqueda por nombre.

    Lo peligroso seria construir "/company//jobs/", que es un 404 con pinta de
    enlace bueno.
    """
    assert company_jobs(malo) is None


def test_un_slug_valido_construye_la_pestana_de_empleo():
    assert company_jobs("clarity-ai") == "https://www.linkedin.com/company/clarity-ai/jobs/"


def test_las_mayusculas_se_normalizan():
    """"Cabify" y "cabify" son el mismo slug, y equivocarse de caja es facil.
    Lo que no se acepta es un NOMBRE de empresa, que lleva espacios."""
    assert company_jobs("Cabify") == "https://www.linkedin.com/company/cabify/jobs/"


def test_todos_los_slugs_del_yaml_son_validos(datos):
    for entrada in datos["empresas"] + datos.get("competencia_detectada", []):
        fichas = entrada.get("empresas") or [entrada]
        for ficha in fichas:
            if isinstance(ficha, str):
                continue
            slug = ficha.get("linkedin_slug")
            if slug is not None:
                assert SLUG.match(slug), f"slug invalido: {slug!r}"


def test_toda_url_de_empresa_del_html_tiene_slug(html):
    for url in _hrefs(html):
        m = re.search(r"/company/([^/]*)/jobs/", url)
        if m:
            assert SLUG.match(m.group(1)), f"slug vacio o raro en {url}"


# --------------------------------------------------------------------------
# Que se enlaza y que no

def test_una_oferta_sin_verificar_no_se_enlaza(datos, html):
    """Es la decision tomada: la URL se guarda, pero no se publica.

    Publicar enlaces que nadie ha abierto es lo que llenaba la pagina de
    paginas muertas.
    """
    sin_verificar = [e["oferta_url"] for e in datos["empresas"]
                     if e.get("oferta_url") and not e.get("oferta_verificada")]
    assert sin_verificar, "el YAML deberia tener ofertas pendientes de comprobar"
    for url in sin_verificar:
        # Se busca el atributo, no la cadena suelta: "Abrir la oferta" tambien
        # aparece dentro del texto de `accion`, que es prosa, no un enlace.
        assert f'href="{url}"' not in html


def test_una_oferta_verificada_si_se_enlaza(datos):
    copia = yaml.safe_load(RUTA_YAML.read_text(encoding="utf-8"))
    objetivo = next(e for e in copia["empresas"] if e.get("oferta_url"))
    objetivo["oferta_verificada"] = True
    salida = render_curated(copia, "t", geo_id="100994331")
    assert objetivo["oferta_url"] in salida
    assert "Abrir la oferta" in salida


def test_la_ficha_sin_empresa_enlaza_un_listado_etiquetado_como_tal(html):
    """No se puede buscar una empresa cuyo nombre no se conoce.

    Lo honesto es el listado del rol, dicho como listado para que nadie lo
    confunda con una oferta concreta.
    """
    assert "(listado)" in html
    assert "keywords=Junior+Product+Designer" in html.replace("&amp;", "&")


def test_ningun_keywords_es_una_frase_de_una_descripcion(html):
    """El caso real: "Junior Product Designer benefits AI-driven mindset".

    Una frase copiada de una oferta como `keywords` devuelve cero resultados.
    Un nombre de empresa o un termino de rol no pasan de cuatro palabras.
    """
    for url in _hrefs(html):
        for valor in parse_qs(urlparse(url).query).get("keywords", []):
            assert len(valor.split()) <= 4, f"keywords demasiado largo: {valor!r}"


def test_el_yaml_no_lleva_slugs_adivinados(datos):
    """Se probo a deducirlos del nombre y no funciona.

    LinkedIn no da 404 en un slug inexistente: redirige a
    /company/unavailable/, que es la pagina de error que se vio al abrirlos.
    Un slug solo entra aqui comprobado, o traido por el scraper desde el propio
    LinkedIn. El valor por defecto es no tener ninguno.
    """
    for entrada in datos["empresas"] + datos.get("competencia_detectada", []):
        for ficha in entrada.get("empresas") or [entrada]:
            if isinstance(ficha, dict):
                assert not ficha.get("linkedin_slug"), ficha.get("nombre")


def test_un_slug_comprobado_da_los_dos_enlaces(datos):
    """Cuando alguien SI ha comprobado un slug, la ficha lleva los dos: la
    pestana de empleo, que acota, y la busqueda por nombre como red."""
    copia = yaml.safe_load(RUTA_YAML.read_text(encoding="utf-8"))
    entrada = next(e for e in copia["empresas"] if e["nombre"] == "Cabify")
    entrada["linkedin_slug"] = "cabify"
    urls = _hrefs(render_curated(copia, "t", geo_id="100994331"))
    assert "https://www.linkedin.com/company/cabify/jobs/" in urls
    assert any(parse_qs(urlparse(u).query).get("keywords") == ["Cabify"] for u in urls)


def test_toda_empresa_tiene_al_menos_un_enlace_que_no_puede_fallar(html, datos):
    """Sin slug, la busqueda por nombre es lo unico que hay. Tiene que estar."""
    urls = _hrefs(html)
    for entrada in datos["empresas"]:
        if entrada.get("sin_busqueda_empresa") or entrada.get("busqueda_rol"):
            continue
        for ficha in entrada.get("empresas") or [entrada]:
            nombre = ficha["nombre"] if isinstance(ficha, dict) else ficha
            assert any(parse_qs(urlparse(u).query).get("keywords") == [nombre]
                       for u in urls), nombre


# --------------------------------------------------------------------------
# La muestra del radar

def test_la_muestra_no_enlaza_ofertas_inventadas(settings):
    """Los ids de la muestra son inventados: un enlace ahi es un 404 seguro."""
    from datetime import date
    from rrhh_tools.http import FixtureFetcher
    from rrhh_tools.pipeline.run import process
    from rrhh_tools.report.render import render_report
    from rrhh_tools.sources import guest

    fetcher = FixtureFetcher(Path(__file__).parent / "fixtures" / "demo")
    queries, _ = settings.resolvable_queries()
    registros, _ = guest.collect(fetcher, queries, settings, 250)
    run = process(registros, settings, "m", today=date(2026, 9, 5))

    muestra = render_report(run, "t", es_muestra=True, publico=True)
    assert "jobs/view/" not in muestra
    assert "Junior Product Designer" in muestra, "el titulo sigue viendose"

    # Un informe real SI enlaza: ahi los ids se han visto de verdad.
    assert "jobs/view/" in render_report(run, "t", es_muestra=False)


# --------------------------------------------------------------------------
# Red de seguridad

DOMINIOS_PERMITIDOS = {
    "www.linkedin.com", "github.com", "fonts.googleapis.com", "fonts.gstatic.com",
}


def test_ningun_enlace_apunta_a_un_dominio_inesperado(html, datos):
    """Catch-all: si aparece un dominio nuevo, que sea una decision consciente."""
    verificadas = {e["oferta_url"] for e in datos["empresas"]
                   if e.get("oferta_url") and e.get("oferta_verificada")}
    for url in _hrefs(html):
        if url in verificadas or url.startswith(("#", "/", "data:")):
            continue
        host = urlparse(url).netloc
        assert host in DOMINIOS_PERMITIDOS, f"dominio inesperado: {host} ({url})"


# --------------------------------------------------------------------------
# El verificador, sin red

def test_recolecta_solo_lo_que_puede_morir(datos):
    """Las busquedas no se comprueban: siempre responden. Cero resultados no
    es un enlace roto."""
    from rrhh_tools.links_check import recolectar
    campos = {e.campo for e in recolectar(datos)}
    assert campos <= {"linkedin_slug", "oferta_url"}
    # Hoy no hay slugs, asi que solo quedan las ofertas por comprobar.
    assert "oferta_url" in campos

    con_slug = yaml.safe_load(RUTA_YAML.read_text(encoding="utf-8"))
    con_slug["empresas"][0]["linkedin_slug"] = "cabify"
    assert "linkedin_slug" in {e.campo for e in recolectar(con_slug)}


def test_un_200_que_redirige_fuera_del_slug_no_cuenta_como_correcto():
    """El caso que un 200 esconde. LinkedIn no da 404 en una empresa que no
    existe: redirige. Sin esto, un slug inventado pasaria por bueno."""
    from rrhh_tools.links_check import OK, REDIRIGIDO, Enlace, juzgar
    e = Enlace("https://www.linkedin.com/company/no-existe/jobs/", "X", "linkedin_slug")
    assert juzgar(e, 200, "https://www.linkedin.com/jobs/").veredicto == REDIRIGIDO
    assert juzgar(e, 200, e.url).veredicto == OK


def test_un_bloqueo_no_se_confunde_con_un_enlace_muerto():
    """Un 403 dice que LinkedIn nos ha parado, no que el enlace este mal.
    Tratarlos igual borraria slugs buenos del YAML."""
    from rrhh_tools.links_check import BLOQUEADO, MUERTO, Enlace, juzgar
    e = Enlace("https://www.linkedin.com/company/cabify/jobs/", "Cabify", "linkedin_slug")
    assert juzgar(e, 403, e.url).veredicto == BLOQUEADO
    assert not juzgar(e, 403, e.url).accionable
    assert juzgar(e, 404, e.url).veredicto == MUERTO
    assert juzgar(e, 200, "https://www.linkedin.com/login").veredicto == BLOQUEADO


def test_el_write_conserva_los_comentarios_del_yaml(tmp_path):
    """Volcar el YAML con PyYAML se cargaria los comentarios, que en ese
    fichero explican que dato es real y cual es una hipotesis."""
    from rrhh_tools.links_check import Enlace, Informe, Resultado, aplicar, OK

    destino = tmp_path / "c.yaml"
    destino.write_text(RUTA_YAML.read_text(encoding="utf-8"), encoding="utf-8")
    datos = yaml.safe_load(destino.read_text(encoding="utf-8"))
    entrada = next(e for e in datos["empresas"] if e.get("oferta_url"))

    informe = Informe([Resultado(
        Enlace(entrada["oferta_url"], entrada["nombre"], "oferta_url"), OK, 200)])
    assert aplicar(destino, informe)

    texto = destino.read_text(encoding="utf-8")
    assert "# QUE ES REAL Y QUE NO" in texto, "los comentarios siguen ahi"
    assert yaml.safe_load(texto)["empresas"][0]["oferta_verificada"] is True


def test_el_write_retira_un_slug_muerto(tmp_path):
    from rrhh_tools.links_check import Enlace, Informe, MUERTO, Resultado, aplicar

    destino = tmp_path / "c.yaml"
    # El YAML de verdad ya no lleva slugs, asi que se anade uno para ejercitar
    # el camino: es lo que pasara cuando alguien comprobado uno y luego muera.
    destino.write_text(
        RUTA_YAML.read_text(encoding="utf-8").replace(
            '  - nombre: "Cabify"\n', '  - nombre: "Cabify"\n    linkedin_slug: "cabify"\n'),
        encoding="utf-8")
    informe = Informe([Resultado(
        Enlace("https://www.linkedin.com/company/cabify/jobs/", "Cabify", "linkedin_slug"),
        MUERTO, 404)])
    assert aplicar(destino, informe)

    datos = yaml.safe_load(destino.read_text(encoding="utf-8"))
    cabify = next(e for e in datos["empresas"] if e["nombre"] == "Cabify")
    assert cabify.get("linkedin_slug") is None, "el slug malo ya no genera enlace"
