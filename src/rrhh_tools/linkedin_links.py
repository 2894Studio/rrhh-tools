"""Enlaces a LinkedIn para verificar cada empresa en la fuente original.

TRES CONSTRUCTORES, UNO POR PROPOSITO, Y NINGUNO MEZCLA DOS COSAS
----------------------------------------------------------------
Esto antes era una sola funcion que pegaba el nombre de la empresa delante de
una cadena de terminos de diseno:

    keywords = "Cabify designer OR diseñador OR UX OR UI"

y estaba roto. LinkedIn solo acota una busqueda a una empresa con la faceta
`f_C=<id numerico>`, que no tenemos; metiendo el nombre como texto libre dentro
de una cadena de OR, la restriccion por empresa se pierde y la busqueda devuelve
o un listado general o nada. Los dos sintomas que se vieron en produccion salian
de esa unica linea.

Asi que ahora hay tres funciones, cada una con un solo trabajo, y el que llama
tiene que elegir a proposito cual usa. Es mas dificil volver a mezclarlas.

QUE ENLACE ACOTA DE VERDAD
--------------------------
  company_jobs(slug)  -> lo unico que acota a una empresa concreta sin conocer
                         su id numerico. Depende de que el slug sea correcto.
  jobs_by_name(...)   -> no acota, pero NUNCA da 404 y siempre lleva a un
                         listado real. Es la red de seguridad.
  jobs_by_role(...)   -> listado general a proposito. Quien lo pinte tiene que
                         etiquetarlo como listado, no como oferta.

Ninguna de las tres inventa una URL de oferta. Un `jobs/view/<id>` solo es
legitimo si el id se ha visto de verdad en LinkedIn.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

JOBS = "https://www.linkedin.com/jobs/search/"
COMPANIES = "https://www.linkedin.com/search/results/companies/"

# Los slugs de LinkedIn son minusculas, digitos y guiones, sin guion al principio
# ni al final. Se valida antes de construir nada para que un slug vacio no acabe
# generando "/company//jobs/", que es un 404 con aspecto de enlace bueno.
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,98}[a-z0-9]$")


def _busqueda(keywords: str, geo_id: str | None) -> str:
    params = {"keywords": keywords}
    if geo_id:
        params["geoId"] = geo_id
    return f"{JOBS}?{urlencode(params)}"


def company_jobs(slug: str | None) -> str | None:
    """Pestana de empleo de una empresa. `None` si el slug no es valido.

    Devolver None en vez de una URL a medias es deliberado: quien llama cae
    entonces en `jobs_by_name`, que no falla nunca.
    """
    slug = (slug or "").strip().strip("/").lower()
    if not SLUG.match(slug):
        return None
    return f"https://www.linkedin.com/company/{slug}/jobs/"


def jobs_by_name(company: str, geo_id: str | None = None) -> str:
    """Busqueda de empleo por nombre de empresa.

    El nombre va SOLO. No se le anaden terminos de diseno: anadirlos es lo que
    rompia el enlace, porque convertia una busqueda de empresa en una cadena de
    OR que LinkedIn resuelve por su cuenta.
    """
    return _busqueda(company.strip(), geo_id)


def jobs_by_role(role: str, geo_id: str | None = None) -> str:
    """Listado de ofertas de un rol en una zona.

    Es un listado GENERAL, y eso no es un defecto sino su proposito. Quien lo
    pinte debe etiquetarlo como listado para no hacerlo pasar por una oferta.
    """
    return _busqueda(role.strip(), geo_id)


def company_search(company: str) -> str:
    """Pagina de la empresa en LinkedIn, via buscador de empresas."""
    return f"{COMPANIES}?{urlencode({'keywords': company.strip()})}"
