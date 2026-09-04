"""Comprobacion de los enlaces que publica el informe.

POR QUE EXISTE ESTE MODULO
--------------------------
El entorno donde se desarrolla la herramienta no llega a LinkedIn: la pasarela
responde 403 al CONNECT. Asi que aqui no se puede saber si un enlace vive. Lo
unico honesto es (a) generar solo formas de URL que sean correctas por
construccion, y (b) dar un comando que se ejecute donde LinkedIn SI es
alcanzable. Esto es (b).

Comprueba exactamente las URLs QUE SE PUBLICAN, reusando los mismos
constructores que el renderer. Si un dia el renderer cambia de enlace, el
verificador cambia con el: no hay dos listas que puedan desincronizarse.

DISCIPLINA DE PETICIONES
------------------------
El mismo ritmo fijo y el mismo navegador que el resto del proyecto: una sola
sesion, en serie, con espera entre peticiones. Sin rotacion, sin paralelismo y
sin ninguna tecnica para esquivar controles. Son unas pocas decenas de
peticiones y se hacen una vez, no en bucle.
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .http import USER_AGENT
from .linkedin_links import company_jobs

# Un veredicto por caso, porque la accion que provocan es distinta.
OK = "ok"                    # responde y no ha huido a otra pagina
MUERTO = "muerto"            # 404 y demas: el enlace no lleva a nada
REDIRIGIDO = "redirigido"    # responde 200 pero ha acabado en otro sitio
BLOQUEADO = "bloqueado"      # 403/429/999 o muro de login: no se puede juzgar
SIN_RESPUESTA = "sin respuesta"


@dataclass
class Enlace:
    """Un enlace publicado, con de donde sale."""

    url: str
    ficha: str
    campo: str  # "linkedin_slug" | "oferta_url" | "busqueda"


@dataclass
class Resultado:
    enlace: Enlace
    veredicto: str
    codigo: int | None = None
    url_final: str | None = None
    nota: str = ""

    @property
    def accionable(self) -> bool:
        """Un enlace que hay que quitar o corregir."""
        return self.veredicto in (MUERTO, REDIRIGIDO)


@dataclass
class Informe:
    resultados: list[Resultado] = field(default_factory=list)

    def por_veredicto(self, veredicto: str) -> list[Resultado]:
        return [r for r in self.resultados if r.veredicto == veredicto]


def recolectar(datos: dict) -> list[Enlace]:
    """Los enlaces que el informe publicaria a partir de este YAML.

    Solo se comprueba lo que puede estar muerto: la pestana de empleo de una
    empresa (depende de que el slug sea correcto) y las URLs de oferta de
    terceros (caducan). Las busquedas por nombre y los listados por rol no se
    comprueban a proposito: son busquedas, siempre responden, y como mucho
    devuelven cero resultados, que no es un enlace roto.
    """
    enlaces: list[Enlace] = []
    for entrada in datos.get("empresas", []):
        nombre = entrada.get("nombre", "")
        crudas = entrada.get("empresas") or [entrada]
        for empresa in crudas:
            if isinstance(empresa, str):
                continue  # sin slug que comprobar
            url = company_jobs(empresa.get("linkedin_slug"))
            if url:
                enlaces.append(Enlace(url, empresa.get("nombre", nombre), "linkedin_slug"))
        if entrada.get("oferta_url"):
            enlaces.append(Enlace(entrada["oferta_url"], nombre, "oferta_url"))
    for ficha in datos.get("competencia_detectada", []):
        url = company_jobs(ficha.get("linkedin_slug"))
        if url:
            enlaces.append(Enlace(url, ficha.get("nombre", ""), "linkedin_slug"))
    return enlaces


def juzgar(enlace: Enlace, codigo: int | None, url_final: str | None) -> Resultado:
    """Traduce una respuesta a un veredicto.

    Esta separado de la peticion para poder probarlo sin red, que es donde
    estan los casos interesantes: un 200 no significa que el enlace sirva.
    """
    if codigo is None:
        return Resultado(enlace, SIN_RESPUESTA, None, None,
                         "no hubo respuesta; puede ser la red y no el enlace")
    if codigo in (403, 429, 999):
        return Resultado(enlace, BLOQUEADO, codigo, url_final,
                         "LinkedIn ha bloqueado la peticion: no dice nada del enlace")
    if codigo >= 400:
        return Resultado(enlace, MUERTO, codigo, url_final)

    final = url_final or enlace.url
    if "/login" in final or "authwall" in final:
        return Resultado(enlace, BLOQUEADO, codigo, final,
                         "ha salido el muro de login; repite con sesion iniciada")

    # El caso que un 200 esconde: LinkedIn no da 404 en una empresa que no
    # existe, redirige a una pagina generica. Si la URL final ya no lleva el
    # slug que pedimos, el slug esta mal por mucho que el codigo sea 200.
    m = re.search(r"/company/([^/?#]+)", enlace.url)
    if m and f"/company/{m.group(1)}" not in final:
        return Resultado(enlace, REDIRIGIDO, codigo, final,
                         f"el slug «{m.group(1)}» acaba en otra pagina")
    return Resultado(enlace, OK, codigo, final)


def comprobar(enlaces: list[Enlace], min_delay: float = 4.0,
              timeout: int = 30, jitter: float = 0.5) -> Informe:
    """Pide cada enlace, en serie y con espera. Requiere red."""
    import requests

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    })
    informe = Informe()
    for i, enlace in enumerate(enlaces):
        if i:
            time.sleep(min_delay + random.uniform(0, jitter))
        try:
            r = session.get(enlace.url, timeout=timeout, allow_redirects=True)
            informe.resultados.append(juzgar(enlace, r.status_code, r.url))
        except Exception as exc:  # noqa: BLE001 - la red falla de muchas formas
            informe.resultados.append(
                Resultado(enlace, SIN_RESPUESTA, None, None, type(exc).__name__))
    return informe


def aplicar(ruta: Path, informe: Informe) -> list[str]:
    """Escribe el resultado en el YAML, por lineas y no volcandolo entero.

    Volcar el YAML con PyYAML perderia todos los comentarios, y en este fichero
    los comentarios son la mitad del valor: explican que es real y que no. Asi
    que se editan las lineas concretas y se deja el resto intacto.
    """
    texto = ruta.read_text(encoding="utf-8")
    cambios: list[str] = []

    for r in informe.por_veredicto(OK):
        if r.enlace.campo != "oferta_url":
            continue
        patron = re.compile(
            r'(oferta_url: "' + re.escape(r.enlace.url) + r'"\n(\s*)oferta_verificada: )false',
        )
        texto, n = patron.subn(r"\1true", texto)
        if n:
            cambios.append(f"{r.enlace.ficha}: oferta comprobada, se publica el enlace")

    for r in informe.resultados:
        if r.enlace.campo != "linkedin_slug" or not r.accionable:
            continue
        slug = re.search(r"/company/([^/?#]+)", r.enlace.url).group(1)
        patron = re.compile(r'( *)(linkedin_slug: "' + re.escape(slug) + r'")([^\n]*)')
        texto, n = patron.subn(
            lambda m: f'{m.group(1)}# slug retirado por links --check '
                      f'({r.veredicto}): {m.group(2)}',
            texto)
        if n:
            cambios.append(f"{r.enlace.ficha}: slug «{slug}» retirado ({r.veredicto})")

    if cambios:
        ruta.write_text(texto, encoding="utf-8")
    return cambios
