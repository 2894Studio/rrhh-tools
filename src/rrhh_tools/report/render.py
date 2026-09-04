"""Render del informe HTML.

Un unico fichero autocontenido salvo la fuente DM Sans, que se pide a Google
Fonts. La pila de respaldo esta puesta para que el informe siga siendo legible
sin conexion o si la fuente no carga.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..linkedin_links import (
    company_jobs, company_search, jobs_by_name, jobs_by_role,
)
from ..logos import por_dominio
from ..models import Company, ProcessedRun
import json

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _badges(company: Company) -> list[str]:
    """Etiquetas cortas de un vistazo. Fieles a lo que dicen los factores."""
    out: list[str] = []
    buckets = {job.location_bucket.value for job in company.jobs}
    if "MADRID" in buckets:
        out.append("Madrid")
    if "REMOTE_ES" in buckets:
        out.append("Remoto España")
    for component in company.components:
        if component.name == "first_designer_signal" and component.value >= 1.0:
            out.append("Su primer diseñador")
        if component.name == "ai_relevance" and component.value >= 0.6:
            out.append("Menciona IA")
    if company.n_jobs > 1:
        out.append(f"{company.n_jobs} vacantes")
    if company.classification.confidence < 0.7:
        out.append("Clasificación dudosa")
    return out


# Facetas del informe del radar. Se declaran aqui, no se derivan del DOM, para
# controlar etiquetas y orden. "nivel" y "rol" son multiseleccion porque se
# querra ver "junior + mid" o "IA + producto" a la vez.
FACETAS_RADAR = [
    {"clave": "nivel", "etiqueta": "Nivel", "multi": True,
     "atajo": {"etiqueta": "Solo junior", "valores": ["junior"]},
     "opciones": [{"valor": "junior", "etiqueta": "Junior"},
                  {"valor": "mid", "etiqueta": "Mid"},
                  {"valor": "senior", "etiqueta": "Senior"},
                  {"valor": "lead", "etiqueta": "Lead"}]},
    {"clave": "rol", "etiqueta": "Rol", "multi": True,
     "opciones": [{"valor": "ai", "etiqueta": "Diseño con IA"},
                  {"valor": "product", "etiqueta": "Producto"},
                  {"valor": "uxui", "etiqueta": "UX/UI"},
                  {"valor": "ux", "etiqueta": "UX"},
                  {"valor": "ui", "etiqueta": "UI"},
                  {"valor": "otro", "etiqueta": "Otro"}]},
    {"clave": "ubicacion", "etiqueta": "Dónde", "multi": False,
     "opciones": [{"valor": "madrid", "etiqueta": "Madrid"},
                  {"valor": "remote_es", "etiqueta": "Remoto España"},
                  {"valor": "rest_es", "etiqueta": "Resto de España"}]},
    {"clave": "dias", "etiqueta": "Publicada", "multi": False, "tipo": "max",
     "opciones": [{"valor": "7", "etiqueta": "7 días"},
                  {"valor": "14", "etiqueta": "14 días"},
                  {"valor": "30", "etiqueta": "30 días"}]},
    {"clave": "ia", "etiqueta": "IA", "multi": False,
     "opciones": [{"valor": "si", "etiqueta": "Menciona IA"}]},
    {"clave": "bloque", "etiqueta": "Bloque", "multi": False,
     "opciones": [{"valor": "A", "etiqueta": "Objetivo"},
                  {"valor": "B", "etiqueta": "Agencias"},
                  {"valor": "C", "etiqueta": "Intermediarios"},
                  {"valor": "D", "etiqueta": "Por revisar"}]},
]

FACETAS_CURADA = [
    {"clave": "evidencia", "etiqueta": "Evidencia", "multi": False,
     "opciones": [{"valor": "oferta", "etiqueta": "Pista de vacante"},
                  {"valor": "confirmada", "etiqueta": "Pista sin empresa"},
                  {"valor": "estrategica", "etiqueta": "Solo empresa"}]},
    {"clave": "ubicacion", "etiqueta": "Dónde", "multi": False,
     "opciones": [{"valor": "madrid", "etiqueta": "Madrid"},
                  {"valor": "espana", "etiqueta": "España / remoto"}]},
]


def _reparto_niveles(run: ProcessedRun) -> dict[str, int]:
    """Cuántas vacantes hay de cada nivel, y cuántas son de diseño con IA.

    Es la mitad que faltaba de la 'temperatura del mercado': antes solo decía
    de quién son las vacantes, no de qué nivel, porque solo había junior.
    """
    reparto = {"junior": 0, "mid": 0, "senior": 0, "lead": 0, "ai": 0}
    for company in (run.targets + run.competition + run.intermediaries + run.review):
        for job in company.jobs:
            if job.seniority:
                clave = job.seniority.label.clave_filtro
                if clave in reparto:
                    reparto[clave] += 1
            if job.rol and job.rol.label.value == "AI":
                reparto["ai"] += 1
    return reparto


def _facetas_json(facetas: list[dict]) -> str:
    """Serializa las facetas para incrustarlas en un <script type=application/json>.

    Se escapa "<" a su forma unicode: es la unica secuencia capaz de cerrar el
    <script> desde dentro. Hoy el contenido son constantes nuestras, pero la
    proteccion cuesta una linea y evita una sorpresa el dia que no lo sean.
    """
    return json.dumps(facetas, ensure_ascii=False).replace("<", "\\u003c")


def _enlace_empresa(company: Company, geo_id: str | None) -> str:
    """Enlace para ver en LinkedIn todas las vacantes de esta empresa.

    Si conocemos su slug vamos directos a su pagina de empleo; si no,
    construimos una busqueda. Nunca inventamos una URL de oferta.
    """
    url = company.linkedin_url or ""
    if "/company/" in url:
        # Aqui el slug NO es adivinado: viene del propio LinkedIn al scrapear.
        slug = company_jobs(url.rstrip("/").split("/company/")[-1].split("?")[0])
        if slug:
            return slug
    return jobs_by_name(company.display_name, geo_id)


# Encabezados de bloque para la version publica. Los del dominio (models.py)
# dicen para que sirve cada bloque en la conversacion comercial ("a quien podeis
# llamar", "estan ganando proyectos"): es nuestra estrategia y no se publica.
# Aqui se sustituyen por el hecho desnudo, que es lo que aporta la muestra.
# Se hace en el renderer, no en la plantilla, por el mismo motivo que la lista
# curada: lo que no este explicitamente traducido no llega al publico por error.
BLOQUES_PUBLICOS = {
    "A": ("Empresas con producto propio",
          "Empresas que contratan diseño para su propio producto."),
    "B": ("Agencias y estudios",
          "Agencias y estudios de diseño con vacantes abiertas."),
    "C": ("Intermediarios",
          "Consultoras y empresas de selección. La oferta no dice para quién es "
          "el puesto, aunque a veces se deja entrever."),
    "D": ("Por revisar",
          "Clasificación ambigua: el sistema no supo resolver de qué tipo de "
          "empresa se trata."),
}


def render_report(run: ProcessedRun, title: str, source_label: str = "LinkedIn",
                  es_muestra: bool = False, geo_id: str | None = None,
                  publico: bool = False) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        # autoescape=True explicito, NO select_autoescape(["html"]): esa funcion
        # mira la extension del fichero, que aqui es ".j2", asi que el escapado
        # no llegaba a activarse nunca y un nombre de empresa con HTML dentro se
        # inyectaba tal cual en el informe.
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.html.j2")

    # Los badges son datos de presentacion, no del dominio: se calculan aqui y
    # viajan aparte, sin ensuciar el modelo Company.
    blocks = []
    for block_id, block_title, description, companies in run.blocks:
        if publico:
            block_title, description = BLOQUES_PUBLICOS[block_id.value]
        blocks.append({
            "id": block_id.value,
            "title": block_title,
            "description": description,
            "rows": [{"c": company, "badges": _badges(company),
                      "linkedin": _enlace_empresa(company, geo_id),
                      "ubicaciones": sorted({j.location_bucket.value.lower()
                                             for j in company.jobs}),
                      "menciona_ia": any(
                          x.name == "ai_relevance" and x.value >= 0.6
                          for x in company.components)}
                     for company in companies],
        })

    _, reconcile_msg = run.reconcile()
    return template.render(
        facetas_json=_facetas_json(FACETAS_RADAR),
        title=title,
        generated=run.generated_at.strftime("%d/%m/%Y %H:%M"),
        run_id=run.run_id,
        config_hash=run.config_hash,
        source_label=source_label,
        # Un informe generado contra fixtures lleva empresas reales con ofertas
        # inventadas. Sin un aviso dentro de la propia pagina se lee como real.
        es_muestra=es_muestra,
        publico=publico,
        counts=run.count_jobs(),
        niveles=_reparto_niveles(run),
        blocks=blocks,
        filtered=run.filtered_jobs,
        diagnostics=run.diagnostics,
        reconcile_msg=reconcile_msg,
    )


# Campos que SI viajan a la version publica. Es una lista de permitidos, no de
# prohibidos, y eso es deliberado: si manana alguien anade un campo al YAML,
# queda fuera del publico por omision en vez de colarse porque nadie actualizo
# una lista de exclusiones o un {% if %} de la plantilla.
CAMPOS_PUBLICOS_EMPRESA = {
    "nombre", "sector", "ubicacion", "vacante", "evidencia", "detalle",
    "dominio", "empresas", "busqueda_rol", "oferta_url", "oferta_verificada",
    "oferta_fuente", "sin_busqueda_empresa", "linkedin_slug",
}
CAMPOS_PUBLICOS_COMPETENCIA = {"nombre", "tipo", "detalle", "dominio",
                               "linkedin_slug"}
# Lo que se queda fuera y por que:
#   por_que  -> por que es objetivo comercial. Es nuestra estrategia.
#   accion   -> el siguiente paso comercial. Idem.
#   lectura  -> nuestra interpretacion de la competencia.


def _publicar(entrada: dict, permitidos: set[str]) -> dict:
    return {k: v for k, v in entrada.items() if k in permitidos}


def _monograma(nombre: str) -> str:
    """Iniciales de respaldo cuando no hay logo fiable."""
    palabras = [p for p in nombre.split() if p[:1].isalnum()]
    if not palabras:
        return "?"
    if len(palabras) == 1:
        return palabras[0][:2].upper()
    return (palabras[0][:1] + palabras[1][:1]).upper()


def _empresas_de(entrada: dict) -> list[dict]:
    """Empresas de una ficha, siempre como dicts.

    `empresas` admite tanto "BBVA" como {nombre, linkedin_slug}: la ficha
    agrupada de banca necesita un slug por empresa, y las demas no.
    """
    crudas = entrada.get("empresas") or [
        {"nombre": entrada.get("nombre", ""),
         "linkedin_slug": entrada.get("linkedin_slug")}
    ]
    return [{"nombre": e, "linkedin_slug": None} if isinstance(e, str) else dict(e)
            for e in crudas]


def _enlaces_curados(entrada: dict, geo_id: str | None, geo_es: str | None) -> list[dict]:
    """Los enlaces de una ficha, cada uno etiquetado con lo que es de verdad.

    La etiqueta es la mitad del arreglo: un listado general no es una oferta, y
    una busqueda no es la ficha de la empresa. Decirlo evita que el enlace
    parezca roto cuando en realidad hace justo lo que puede hacer.

    Por empresa salen hasta dos enlaces:
      1. su pestana de empleo, que es lo unico que acota de verdad;
      2. la busqueda por nombre, que no acota pero nunca falla.
    Se ponen los dos a proposito: los slugs estan sin verificar, asi que el
    segundo enlace es la red bajo el primero.
    """
    ubicacion = (entrada.get("ubicacion") or "").lower()
    en_madrid = "madrid" in ubicacion
    geo = geo_id if en_madrid else (geo_es or geo_id)
    donde = "Madrid" if en_madrid else "España"
    enlaces: list[dict] = []

    # Una oferta concreta solo se enlaza si alguien la ha abierto y sigue viva.
    # Publicar una URL sin comprobar es lo que llenaba la pagina de enlaces
    # muertos; la URL se conserva en el YAML, esperando a `links --check`.
    if entrada.get("oferta_url") and entrada.get("oferta_verificada"):
        enlaces.append({"texto": "Abrir la oferta", "url": entrada["oferta_url"]})

    # Ficha sin empresa identificada: lo unico honesto es el listado del rol,
    # dicho como listado. Buscar el nombre no daria nada, porque no es un nombre.
    rol = entrada.get("busqueda_rol")
    if rol:
        enlaces.append({"texto": f"Ofertas de {rol} en {donde} (listado)",
                        "url": jobs_by_role(rol, geo)})
        return enlaces
    if entrada.get("sin_busqueda_empresa"):
        return enlaces

    empresas = _empresas_de(entrada)
    varias = len(empresas) > 1
    for empresa in empresas:
        nombre = (empresa.get("nombre") or "").strip()
        if not nombre:
            continue
        ficha = company_jobs(empresa.get("linkedin_slug"))
        if ficha:
            enlaces.append({"texto": f"Vacantes de {nombre} en LinkedIn", "url": ficha})
        enlaces.append({
            "texto": f"Buscar «{nombre}» en LinkedIn" if varias or ficha
                     else "Ver vacantes en LinkedIn",
            "url": jobs_by_name(nombre, geo),
        })
    return enlaces


def _busquedas_vivas(datos: dict, geo_id: str | None, geo_es: str | None) -> list[dict]:
    """Enlaces a busquedas de LinkedIn por rol.

    Es la unica parte de esta pagina que NO puede quedarse obsoleta: no afirma
    que exista ninguna vacante, lleva al estado real de LinkedIn en el momento
    del clic. Cuando una ficha de empresa se equivoca -y se han equivocado-,
    esto sigue sirviendo.
    """
    salida = []
    for b in datos.get("busquedas", []):
        en_madrid = b.get("geo") == "madrid"
        salida.append({
            "rol": b["rol"],
            "donde": "Madrid" if en_madrid else "España",
            "url": jobs_by_role(b["rol"], geo_id if en_madrid else geo_es),
        })
    return salida


def _enlaces_competencia(ficha: dict) -> list[dict]:
    """Igual que en las fichas de empresa: pestana de empleo si hay slug, y si
    no la busqueda de empresas, que tambien lleva a algo real."""
    nombre = ficha.get("nombre", "")
    empleo = company_jobs(ficha.get("linkedin_slug"))
    if empleo:
        return [{"texto": f"Vacantes de {nombre} en LinkedIn", "url": empleo}]
    return [{"texto": "Buscar en LinkedIn", "url": company_search(nombre)}]


def render_curated(data: dict, title: str, geo_id: str | None = None,
                   geo_es: str | None = None, publico: bool = False) -> str:
    """Informe de la lista curada inicial.

    Con `publico=True` se recorta el razonamiento comercial: quedan las empresas,
    sus datos y los enlaces para verificarlas en LinkedIn, y desaparece por que
    son objetivo y cual es el siguiente paso. El recorte se hace AQUI y con una
    lista de permitidos, no con condicionales en la plantilla, para que un campo
    nuevo no se publique por descuido.
    """
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    empresas = [
        _publicar(e, CAMPOS_PUBLICOS_EMPRESA) if publico else dict(e)
        for e in data.get("empresas", [])
    ]
    for entrada in empresas:
        entrada["enlaces"] = _enlaces_curados(entrada, geo_id, geo_es)
        entrada["logo"] = por_dominio(entrada.get("dominio"))
        entrada["monograma"] = _monograma(entrada.get("nombre", ""))
        ubic = (entrada.get("ubicacion") or "").lower()
        entrada["clave_ubicacion"] = "madrid" if "madrid" in ubic else "espana"
    # Tres niveles de evidencia, y la diferencia importa mucho: una oferta
    # concreta con URL no es lo mismo que una hipotesis razonada sobre una
    # empresa. Mezclarlas hace que la lista entera parezca mas solida de lo que
    # es, que es justo el error que hay que evitar aqui.
    ofertas = [e for e in empresas if e.get("evidencia") == "oferta"]
    confirmadas = [e for e in empresas if e.get("evidencia") == "confirmada"]
    estrategicas = [e for e in empresas if e.get("evidencia") == "estrategica"]

    # Las cabeceras tambien cambian en publico: "objetivo estrategico" sigue
    # siendo framing comercial aunque el razonamiento ya no este.
    grupos = []
    if ofertas:
        # Estas fichas AFIRMAN que existe una vacante concreta, y esa afirmacion
        # sale de busqueda web, no de LinkedIn, y nunca se ha podido abrir. Ha
        # fallado en la practica: alguna de estas vacantes ya no existe o nunca
        # fue exacta. Asi que el encabezado deja de decir "oferta encontrada",
        # que se leia como un hecho comprobado, y dice lo que es.
        comprobadas = [e for e in ofertas if e.get("oferta_verificada")]
        grupos.append({
            "tag": "Sin comprobar" if not comprobadas else "Pistas de vacante",
            "titulo": "Pistas de vacante, sin comprobar",
            "descripcion": "Vacantes que aparecieron en búsqueda web. NO se han abierto "
                           "ni verificado en LinkedIn, así que el puesto puede estar "
                           "cerrado o el dato ser inexacto. Trátalas como una pista para "
                           "mirar la empresa, no como una oferta abierta.",
            "empresas": ofertas,
        })
    if confirmadas:
        grupos.append({
            "tag": "Sin comprobar",
            "titulo": "Pista sin empresa",
            "descripcion": "Apareció una vacante en búsqueda web pero la fuente no publica "
                           "quién la ofrece, y tampoco se ha podido verificar. Se dice así "
                           "en vez de adivinarlo.",
            "empresas": confirmadas,
        })
    if estrategicas:
        grupos.append({
            "tag": "Sin oferta encontrada",
            "titulo": "Por verificar",
            "descripcion": (
                "Empresas con producto digital propio en España a las que no se les ha "
                "encontrado ninguna vacante abierta. Compruébalo en LinkedIn."
                if publico else
                "NO hay oferta. Son clientes finales con producto digital propio y "
                "necesidad plausible: hipótesis razonadas, no hechos."
            ),
            "empresas": estrategicas,
        })

    return env.get_template("curated.html.j2").render(
        title=title,
        publico=publico,
        facetas_json=_facetas_json(FACETAS_CURADA),
        contexto=data.get("contexto", {}),
        busquedas=_busquedas_vivas(data, geo_id, geo_es),
        grupos=grupos,
        competencia=[
            {**(_publicar(c, CAMPOS_PUBLICOS_COMPETENCIA) if publico else dict(c)),
             "enlaces": _enlaces_competencia(c),
             "logo": por_dominio(c.get("dominio")),
             "monograma": _monograma(c.get("nombre", ""))}
            for c in data.get("competencia_detectada", [])
        ],
        n_ofertas=len(ofertas),
        n_confirmadas=len(confirmadas),
        n_estrategicas=len(estrategicas),
    )


def render_index(generado: str, title: str, publico: bool = False) -> str:
    """Portada del sitio estático que agrupa los informes."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template("index.html.j2").render(
        title=title, generado=generado, publico=publico)
