"""Versión pública de la lista curada.

El sitio está en internet abierto y no se le puede activar protección desde
aquí, así que lo que se publica no puede llevar el razonamiento comercial:
qué empresa es objetivo, por qué, y cuál es el siguiente paso.

El recorte se hace con una LISTA DE PERMITIDOS. Estos tests fijan justamente
eso: que un campo nuevo quede fuera por omisión.
"""

from pathlib import Path

import pytest
import yaml

from rrhh_tools.report.render import (
    CAMPOS_PUBLICOS_COMPETENCIA, CAMPOS_PUBLICOS_EMPRESA, render_curated,
)


def _plano(texto: str) -> str:
    """Texto comparable: sin entidades HTML y con los espacios colapsados.

    Hace falta porque la plantilla escapa las comillas tipográficas y parte las
    frases en varias líneas; comparar en crudo daría falsos negativos.
    """
    import html
    import re
    return re.sub(r"\s+", " ", html.unescape(texto))

DATOS = yaml.safe_load(
    (Path(__file__).parents[1] / "config" / "curated_targets.yaml").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def publico():
    return render_curated(dict(DATOS), "t", geo_id="100994331", geo_es="105646813",
                          publico=True)


@pytest.fixture(scope="module")
def completo():
    return render_curated(dict(DATOS), "t", geo_id="100994331", geo_es="105646813")


def _fragmentos(campo: str) -> list[str]:
    """Trozos reales del YAML, no frases escritas a mano.

    Escribir la lista a mano dejaría un agujero en cuanto alguien añadiera una
    empresa nueva: su razonamiento se publicaría y ningún test se enteraría.
    """
    salida = []
    for entrada in DATOS["empresas"] + DATOS["competencia_detectada"]:
        valor = (entrada.get(campo) or "").strip()
        if len(valor) > 40:
            salida.append(valor[:60])
    return salida


@pytest.mark.parametrize("campo", ["por_que", "accion", "lectura"])
def test_el_razonamiento_comercial_no_se_publica(campo, publico):
    plano = _plano(publico)
    for fragmento in _fragmentos(campo):
        assert _plano(fragmento) not in plano, f"se publicó {campo}: {fragmento!r}"


@pytest.mark.parametrize("campo", ["por_que", "accion", "lectura"])
def test_el_informe_completo_si_lo_conserva(campo, completo):
    """El recorte es solo para publicar; el entregable de trabajo no pierde nada."""
    plano = _plano(completo)
    fragmentos = _fragmentos(campo)
    assert fragmentos, f"el YAML debería tener algún {campo} con contenido"
    for fragmento in fragmentos:
        assert _plano(fragmento) in plano, fragmento


def test_lo_util_se_conserva_en_publico(publico):
    for entrada in DATOS["empresas"]:
        assert entrada["nombre"][:20] in publico
        if entrada.get("sector"):
            assert entrada["sector"] in publico
    assert "linkedin.com/jobs/search" in publico
    assert "icons.duckduckgo.com" in publico, "los logos se quedan"


def test_el_aviso_de_fiabilidad_se_conserva(publico):
    """Es honestidad sobre el dato, no estrategia: no se recorta."""
    plano = _plano(publico)
    assert "no sale de LinkedIn" in plano
    assert "no están comprobadas" in plano
    assert "llevan al estado real de LinkedIn" in plano


def test_el_framing_comercial_desaparece(publico, completo):
    assert "empresas a las que llamar" in _plano(completo)
    assert "empresas a las que llamar" not in _plano(publico)
    assert "Señal de competencia" in completo
    assert "Señal de competencia" not in publico


FRASES_PROHIBIDAS = [
    "Objetivo estratégico", "hipótesis razonadas", "empresas a las que llamar",
    "Señal de competencia", "Siguiente paso", "Por qué:", "menos prioritaria",
    "compite con 2894", "objetivo comercial",
]


def test_ninguna_frase_de_estrategia_llega_a_publico(publico):
    """La lista de permitidos protege de campos NUEVOS, no de que un campo
    permitido lleve juicio dentro.

    Pasó de verdad: el `detalle` de una consultora decía "compite con 2894", y
    `detalle` sí se publica. El arreglo fue mover el juicio a `lectura`; este
    test es lo que impide que vuelva a colarse por ahí.
    """
    plano = _plano(publico)
    encontradas = [f for f in FRASES_PROHIBIDAS if f in plano]
    assert not encontradas, encontradas


def test_las_frases_de_estrategia_si_estan_en_el_completo(completo):
    plano = _plano(completo)
    assert any(f in plano for f in FRASES_PROHIBIDAS)


def test_un_campo_nuevo_no_se_publica_por_descuido():
    """La razón de ser de la lista de permitidos.

    Si mañana alguien añade `notas_internas` al YAML, no debe aparecer en la
    página pública sin que nadie lo decida.
    """
    datos = {
        "contexto": {}, "competencia_detectada": [],
        "empresas": [{
            "nombre": "Acme", "sector": "SaaS", "ubicacion": "Madrid",
            "evidencia": "estrategica", "por_que": "Motivo interno.",
            "notas_internas": "PRESUPUESTO ESTIMADO 40K, CONTACTO EN EL COMITE",
        }],
    }
    salida = render_curated(datos, "t", publico=True)
    assert "PRESUPUESTO" not in salida
    assert "Motivo interno" not in salida
    assert "Acme" in salida, "lo permitido sí debe salir"

    assert "notas_internas" not in CAMPOS_PUBLICOS_EMPRESA
    assert "por_que" not in CAMPOS_PUBLICOS_EMPRESA
    assert "lectura" not in CAMPOS_PUBLICOS_COMPETENCIA


def test_la_muestra_publicada_no_juzga_a_empresas_reales(settings, tmp_path):
    """El radar de muestra usa empresas inventadas.

    Publicar que una empresa real 'no es cliente final', o puntuarla con un 92
    bajo nuestra marca y en abierto, no procede.
    """
    from datetime import date
    from rrhh_tools.http import FixtureFetcher
    from rrhh_tools.pipeline.run import process
    from rrhh_tools.report.render import render_report
    from rrhh_tools.sources import guest

    fixtures = Path(__file__).parent / "fixtures" / "demo"
    fetcher = FixtureFetcher(fixtures)
    queries, _ = settings.resolvable_queries()
    registros, _ = guest.collect(fetcher, queries, settings, 250)
    html = render_report(process(registros, settings, "m", today=date(2026, 9, 5)),
                         "t", es_muestra=True)

    reales = [c["name"] for c in settings.denylist["companies"]]
    reales += [c["name"] for c in settings.allowlist["companies"]]
    for nombre in reales:
        assert nombre not in html, f"la muestra publicada menciona a {nombre}"
    assert "inventadas" in html, "y debe decir que es una muestra"


def test_los_tres_niveles_de_evidencia_no_se_mezclan(completo):
    """Una oferta concreta con URL no es lo mismo que una hipótesis.

    Mezclarlas haría que la lista entera pareciese más sólida de lo que es,
    que es justo el error a evitar en un documento comercial.
    """
    for titulo in ["Pistas de vacante, sin comprobar", "Pista sin empresa", "Por verificar"]:
        assert titulo in completo, titulo


def test_solo_se_enlaza_la_oferta_que_alguien_ha_abierto(publico, completo):
    """CAMBIO DE CRITERIO, no un test relajado.

    Antes se enlazaba toda `oferta_url`. Esas URLs salen de búsqueda web y
    nunca se pudieron abrir desde el entorno de desarrollo —la red las bloquea—,
    y además una oferta muere en cuanto se cubre el puesto: la página acabó
    llena de enlaces a páginas muertas.

    Ahora el enlace depende de `oferta_verificada`, que pone `links --check`
    tras abrir la URL de verdad. La URL sigue en el YAML: no se pierde el
    hallazgo, solo se deja de publicar hasta comprobarlo.
    """
    con_url = [e for e in DATOS["empresas"] if e.get("oferta_url")]
    assert con_url, "debería haber alguna oferta con URL"
    for entrada in con_url:
        for salida in (publico, completo):
            enlazada = f'href="{entrada["oferta_url"]}"' in salida
            assert enlazada == bool(entrada.get("oferta_verificada")), entrada["nombre"]


def test_se_distingue_lo_encontrado_de_lo_supuesto(publico):
    """CAMBIO DE CRITERIO: "Oferta encontrada" se leía como un hecho.

    No lo era. Esas vacantes salen de búsqueda web, nunca se abrieron, y en la
    práctica alguna ya no existía. La etiqueta ahora dice lo que es, y solo
    pasa a "comprobada" cuando `links --check` la ha abierto de verdad.
    """
    plano = _plano(publico)
    assert "Oferta encontrada" not in plano
    assert "Sin comprobar" in plano
    assert "no como una oferta abierta" in plano


def test_las_busquedas_vivas_van_las_primeras(publico):
    """Es lo único de la página que no puede quedarse viejo, así que abre.

    Cuando una ficha se equivoca —y se han equivocado—, estos enlaces siguen
    llevando a lo que hay publicado hoy.
    """
    plano = _plano(publico)
    assert "Ofertas abiertas ahora mismo" in plano
    assert plano.index("Ofertas abiertas ahora mismo") < plano.index("Cómo está el mercado")
    assert "keywords=Product+Designer" in publico


def test_ninguna_ficha_sin_oferta_aparenta_tener_una():
    """Una entrada `estrategica` no debe llevar URL de oferta ni vacante."""
    for entrada in DATOS["empresas"]:
        if entrada.get("evidencia") == "estrategica":
            assert not entrada.get("oferta_url"), entrada["nombre"]
            assert not entrada.get("vacante"), entrada["nombre"]


def _muestra(settings, publico: bool) -> str:
    from datetime import date
    from rrhh_tools.http import FixtureFetcher
    from rrhh_tools.pipeline.run import process
    from rrhh_tools.report.render import render_report
    from rrhh_tools.sources import guest

    fetcher = FixtureFetcher(Path(__file__).parent / "fixtures" / "demo")
    queries, _ = settings.resolvable_queries()
    registros, _ = guest.collect(fetcher, queries, settings, 250)
    return render_report(process(registros, settings, "m", today=date(2026, 9, 5)),
                         "t", es_muestra=True, publico=publico)


# Empresas inventadas evitan juzgar a nadie real, pero no tapan la otra fuga:
# los encabezados del radar explican para qué sirve cada bloque en NUESTRA
# conversación comercial. Eso es estrategia, y en abierto sobra.
FRASES_DE_ESTRATEGIA_DEL_RADAR = [
    "A quién podéis llamar",
    "colocar los perfiles",
    "Señal de competencia",
    "están ganando proyectos",
    "Ellos buscan. Nosotros presentamos.",
    "prepara la conversación",
]


@pytest.mark.parametrize("frase", FRASES_DE_ESTRATEGIA_DEL_RADAR)
def test_el_radar_publico_no_explica_nuestra_estrategia(settings, frase):
    assert _plano(frase) not in _plano(_muestra(settings, publico=True))


@pytest.mark.parametrize("frase", FRASES_DE_ESTRATEGIA_DEL_RADAR)
def test_el_radar_interno_si_la_explica(settings, frase):
    """El informe de trabajo no se toca: es donde vive el razonamiento."""
    assert _plano(frase) in _plano(_muestra(settings, publico=False))


def test_el_radar_publico_conserva_los_hechos(settings):
    """Se recorta la lectura comercial, no el dato ni el formato."""
    html = _muestra(settings, publico=True)
    assert "Vela Health" in html          # las fichas siguen ahí
    assert "Junior Product Designer" in html
    assert "data-nivel=" in html          # y los filtros también
    assert "inventadas" in html           # con su aviso de muestra
