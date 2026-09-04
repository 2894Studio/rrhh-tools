"""Interfaz de linea de comandos.

`search` es el UNICO subcomando que puede abrir una conexion. Todo lo demas
trabaja sobre lo que ya hay en data/, y por eso se puede iterar sobre el
analisis sin volver a pedirle nada a LinkedIn.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .config import ConfigError, load_settings
from .http import AuthWall, FixtureFetcher, ThrottledFetcher, ThrottleStop
from .models import RunDiagnostics
from .pipeline.run import process
from .report.render import render_curated, render_index, render_report
from .store import cache


def _settings(args):
    return load_settings(args.config)


def _geo(settings, nombre: str) -> str | None:
    """geoId si esta resuelto; None si sigue siendo un placeholder.

    Los enlaces sin geoId siguen funcionando: buscan en todo LinkedIn.
    """
    try:
        return settings.geo_id(nombre)
    except ConfigError:
        return None


def _geo_madrid(settings) -> str | None:
    return _geo(settings, "comunidad_madrid")


def _load_env() -> None:
    """Lee .env sin dependencias externas."""
    path = Path(".env")
    if not path.is_file():
        return
    import os
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


# ----------------------------------------------------------------------
def cmd_doctor(args) -> int:
    """Comprueba que todo esta listo ANTES de tocar LinkedIn.

    Existe porque el fallo mas caro es descubrir a mitad de una tirada que la
    cookie no estaba puesta o que un geoId apuntaba a otra region.
    """
    _load_env()
    import os
    fallos, avisos = [], []

    print("Comprobaciones previas\n")

    # --- configuracion ---
    try:
        settings = _settings(args)
        print(f"  [ok]  Configuracion cargada ({settings.config_dir})")
        print(f"  [ok]  Pesos del scoring suman {sum(settings.weights.values()):.0f}")
    except ConfigError as exc:
        print(f"  [FALLO] Configuracion: {exc}")
        return 2

    # --- geoIds y busquedas ---
    lanzables, bloqueadas = settings.resolvable_queries()
    if bloqueadas:
        fallos.append("hay busquedas con el geoId sin resolver")
        print(f"  [FALLO] {len(bloqueadas)} busquedas bloqueadas por un geoId sin resolver:")
        for b in bloqueadas:
            print(f"          {b.splitlines()[0]}")
    else:
        print(f"  [ok]  Las {len(lanzables)} busquedas configuradas son lanzables")
    for nombre, valor in settings.raw["search"]["geo"].items():
        print(f"          geo {nombre}: {valor}")
    avisos.append(
        "Verifica los geoId en la primera tirada: filtra por esa ubicacion en "
        "LinkedIn y compara el parametro geoId= de la URL. Uno equivocado busca "
        "en otra region sin dar ningun error."
    )

    # --- cookie ---
    if args.source == "session":
        cookie = os.environ.get("LINKEDIN_LI_AT", "").strip()
        if not cookie:
            fallos.append("falta la cookie li_at")
            print("  [FALLO] Falta LINKEDIN_LI_AT. Copia .env.example a .env y pega tu cookie.")
        elif len(cookie) < 20:
            fallos.append("la cookie li_at parece incompleta")
            print(f"  [FALLO] LINKEDIN_LI_AT parece incompleta ({len(cookie)} caracteres).")
        else:
            # Nunca se imprime el valor.
            print(f"  [ok]  Cookie li_at presente ({len(cookie)} caracteres)")
            avisos.append(
                "La cookie caduca cada pocas semanas. Si la ejecucion aborta con "
                "'muro de login', copia una nueva."
            )
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                navegador = pw.chromium.launch(headless=True)
                navegador.close()
            print("  [ok]  Playwright y Chromium funcionan")
        except Exception as exc:  # noqa: BLE001
            fallos.append("Chromium no arranca")
            print(f"  [FALLO] Chromium no arranca ({type(exc).__name__}). "
                  "Ejecuta:  uv run playwright install chromium")
    else:
        print("  [--]  Modo publico: no hace falta cookie ni navegador")

    # --- disciplina de peticiones ---
    run = settings.run
    print(f"  [ok]  Ritmo: {run['min_delay_seconds']}s entre peticiones, "
          f"tope {run['max_jobs_per_run']} ofertas por tirada")

    print()
    for aviso in avisos:
        print(f"  aviso: {aviso}")
    if fallos:
        print(f"\n{len(fallos)} problema(s) que impiden la ejecucion: "
              + "; ".join(fallos))
        return 1
    print("\nTodo listo. Empieza con una tirada corta:")
    print(f"  rrhh-tools search --source {args.source} --max-jobs 25 --record")
    return 0


def _es_fallo_de_red(exc: BaseException) -> bool:
    """Distingue un problema de conexion de un error del programa.

    Se mira por nombre para no importar requests aqui solo por esto.
    """
    nombres = {type(e).__name__ for e in _cadena(exc)}
    return bool(nombres & {"ConnectionError", "ProxyError", "SSLError", "Timeout",
                           "ConnectTimeout", "ReadTimeout", "OSError", "socket.gaierror"})


def _cadena(exc: BaseException) -> list[BaseException]:
    salida, actual = [], exc
    while actual is not None and actual not in salida:
        salida.append(actual)
        actual = actual.__cause__ or actual.__context__
    return salida


def cmd_search(args) -> int:
    _load_env()
    settings = _settings(args)
    if args.dias:
        # La config trae 24h porque esta pensada para una tirada DIARIA. En la
        # primera ejecucion esa ventana deja casi todo fuera y parece que la
        # herramienta no encuentra nada, cuando lo que pasa es que solo mira
        # lo publicado hoy.
        settings.raw["search"]["date_posted"] = f"r{args.dias * 86400}"
        print(f"Ventana de publicación: últimos {args.dias} días.")
    queries, blocked = settings.resolvable_queries()
    for message in blocked:
        print(f"[omitida] {message}\n", file=sys.stderr)
    if not queries:
        print("Ninguna búsqueda es lanzable. Resuelve los geoId en config/config.yaml.",
              file=sys.stderr)
        return 2

    run_id = args.run_id or cache.new_run_id()
    max_jobs = args.max_jobs or settings.run["max_jobs_per_run"]
    diagnostics = RunDiagnostics()
    record_dir = Path("data/raw") / run_id if args.record else None

    records: list = []
    seen: set[str] = set()
    if args.resume:
        seen = set(cache.load_checkpoint(run_id).get("seen_ids", []))
        print(f"Reanudando: {len(seen)} ofertas ya vistas se omitirán.")

    try:
        if args.source == "session":
            from .sources import session
            records, labels = session.collect(queries, settings, max_jobs, seen, record_dir,
                                              fetch_details=not args.no_details)
        else:
            from .sources import guest
            fetcher = ThrottledFetcher(
                min_delay=settings.run["min_delay_seconds"],
                jitter=settings.run["jitter_seconds"],
                timeout=settings.run["request_timeout_seconds"],
                max_retries=settings.run["max_retries_on_throttle"],
                record_dir=record_dir,
            )
            records, labels = guest.collect(fetcher, queries, settings, max_jobs, seen,
                                            fetch_details=not args.no_details)
            diagnostics.pages_fetched = fetcher.pages_fetched
    except AuthWall as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 3
    except ThrottleStop as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        cache.save_checkpoint(run_id, {"seen_ids": sorted(seen)})
        return 4
    except Exception as exc:  # noqa: BLE001
        # Un cortafuegos o un proxy corporativo son el fallo mas probable en una
        # maquina nueva, y una traza de 30 lineas no dice cual de los dos es.
        if not _es_fallo_de_red(exc):
            raise
        print(f"\nNo se ha podido conectar con LinkedIn: {type(exc).__name__}.\n"
              "Suele ser una de estas tres:\n"
              "  - un proxy o cortafuegos de la empresa que bloquea linkedin.com\n"
              "  - estar detrás de una VPN que lo filtra\n"
              "  - no haber salida a internet en esta máquina\n"
              "Compruébalo abriendo www.linkedin.com en el navegador de esta misma\n"
              "máquina. Lo descargado hasta ahora queda guardado.\n", file=sys.stderr)
        cache.save_raw(run_id, records)
        cache.save_checkpoint(run_id, {"seen_ids": sorted(seen)})
        return 5

    diagnostics.queries_run = labels
    cache.save_raw(run_id, records)
    cache.save_checkpoint(run_id, {"seen_ids": sorted(seen)})
    print(f"Ejecución {run_id}: {len(records)} ofertas guardadas en {cache.run_dir(run_id)}")
    return 0


def cmd_process(args) -> int:
    settings = _settings(args)
    run_id = cache.resolve_run(args.run)
    records = cache.load_raw(run_id)
    run = process(records, settings, run_id)
    ok, message = run.reconcile()
    counts = run.count_jobs()
    print(f"Ejecución {run_id}")
    print(f"  A cuentas objetivo : {len(run.targets):3}  empresas / {counts['A']} vacantes")
    print(f"  B competencia      : {len(run.competition):3}  empresas / {counts['B']} vacantes")
    print(f"  C intermediarios   : {len(run.intermediaries):3}  empresas / {counts['C']} vacantes")
    print(f"  D por revisar      : {len(run.review):3}  empresas / {counts['D']} vacantes")
    print(f"  descartadas        : {counts['filtered']}")
    print(f"  reconciliación     : {'OK' if ok else 'FALLA'} — {message}")
    return 0 if ok else 5


def cmd_report(args) -> int:
    settings = _settings(args)
    run_id = cache.resolve_run(args.run)
    run = process(cache.load_raw(run_id), settings, run_id,
                  orden=args.orden or settings.report.get("orden", "reciente"))
    html = render_report(run, settings.report["title"], source_label=args.source_label,
                         geo_id=_geo_madrid(settings))
    out = Path(args.out or f"reports/{date.today().isoformat()}-{run_id}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Informe escrito en {out}")
    return 0


def cmd_replay(args) -> int:
    """Pipeline completo contra fixtures. Sin red, ni un solo socket."""
    settings = _settings(args)
    from .sources import guest
    fetcher = FixtureFetcher(Path(args.fixtures))
    queries, _ = settings.resolvable_queries()
    if args.query_id:
        queries = [q for q in queries if q.id == args.query_id]
    records, labels = guest.collect(fetcher, queries, settings, args.max_jobs or 250)
    diagnostics = RunDiagnostics(queries_run=labels, pages_fetched=fetcher.pages_fetched)
    run = process(records, settings, "replay", diagnostics,
                  today=date.fromisoformat(args.today) if args.today else None,
                  orden=args.orden or settings.report.get("orden", "reciente"))
    html = render_report(run, settings.report["title"],
                         source_label="fixtures (sin red)", es_muestra=True,
                         geo_id=_geo_madrid(settings))
    out = Path(args.out or "reports/replay.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    ok, message = run.reconcile()
    print(f"Replay: {len(records)} ofertas · reconciliación {'OK' if ok else 'FALLA'} — {message}")
    print(f"Informe escrito en {out}")
    return 0 if ok else 5


def cmd_curated(args) -> int:
    """Renderiza la lista curada inicial desde config/curated_targets.yaml."""
    import yaml
    settings = _settings(args)
    path = Path(args.data or settings.config_dir / "curated_targets.yaml")
    if not path.is_file():
        print(f"No existe el fichero de la lista curada: {path}", file=sys.stderr)
        return 1
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    html = render_curated(data, "2894 — Empresas objetivo",
                          geo_id=_geo_madrid(settings), geo_es=_geo(settings, "spain"),
                          publico=args.publico)
    out = Path(args.out or "reports/empresas-objetivo.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Lista curada escrita en {out}")
    return 0


def cmd_site(args) -> int:
    """Monta el sitio estático: portada + lista curada + muestra del radar."""
    import shutil
    import yaml
    settings = _settings(args)
    out = Path(args.out or "site")
    out.mkdir(parents=True, exist_ok=True)

    datos = yaml.safe_load(
        (settings.config_dir / "curated_targets.yaml").read_text(encoding="utf-8"))
    (out / "empresas-objetivo.html").write_text(
        render_curated(datos,
                       "2894 — Diseño en España" if args.publico else "2894 — Empresas objetivo",
                       geo_id=_geo_madrid(settings), geo_es=_geo(settings, "spain"),
                       publico=args.publico),
        encoding="utf-8")

    # Por defecto la muestra sale de las fixtures FICTICIAS: el sitio publicado
    # no debe juzgar a empresas reales en internet abierto.
    # La muestra publica y la interna van a ficheros DISTINTOS a proposito: si
    # compartieran nombre, una muestra generada antes en modo interno se
    # reutilizaria tal cual y el sitio publico saldria con el razonamiento
    # comercial dentro sin que nada avisara.
    por_defecto = "muestra-publica.html" if args.publico else "muestra.html"
    radar = Path(args.radar) if args.radar else Path("reports") / por_defecto
    if not radar.is_file() and radar.name == por_defecto and not args.radar:
        _generar_muestra(settings, radar, publico=args.publico)
    if radar.is_file():
        shutil.copy(radar, out / "radar.html")
    else:
        print(f"Aviso: no se encontró {radar}; el sitio saldrá sin la muestra del radar.",
              file=sys.stderr)

    (out / "index.html").write_text(
        render_index(date.today().strftime("%d/%m/%Y"), "2894 — Radar de diseño",
                     publico=args.publico),
        encoding="utf-8")

    # Las tres paginas comparten la misma hoja de estilos, que va embebida en
    # cada una para que el fichero suelto siga siendo autocontenido. En el sitio
    # se extrae a styles.css: el navegador la descarga una vez y la cachea.
    _share_stylesheet(out)
    _share_script(out)
    print(f"Sitio montado en {out}/")
    return 0


def _generar_muestra(settings, destino: Path, publico: bool = False) -> None:
    """Genera la muestra del radar desde las fixtures ficticias."""
    from .http import FixtureFetcher
    from .sources import guest
    fixtures = Path("tests/fixtures/demo")
    if not fixtures.is_dir():
        print(f"Aviso: no existe {fixtures}; el sitio saldrá sin la muestra del radar.",
              file=sys.stderr)
        return
    fetcher = FixtureFetcher(fixtures)
    queries, _ = settings.resolvable_queries()
    records, labels = guest.collect(fetcher, queries, settings, 250)
    diagnostics = RunDiagnostics(queries_run=labels, pages_fetched=fetcher.pages_fetched)
    run = process(records, settings, "muestra", diagnostics)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        render_report(run, settings.report["title"],
                      source_label="datos de muestra", es_muestra=True,
                      geo_id=_geo_madrid(settings), publico=publico),
        encoding="utf-8")


def _share_script(out: Path) -> None:
    """El script de filtros es identico en los dos informes: se extrae a un
    fichero para que el navegador lo descargue una vez y lo cachee.

    Igual que con la hoja de estilos, cada informe suelto lo sigue llevando
    embebido para seguir siendo autocontenido; solo el sitio lo separa.
    """
    import re
    paginas = sorted(out.glob("*.html"))
    cuerpo = None
    for pagina in paginas:
        html = pagina.read_text(encoding="utf-8")
        bloques = [b for b in re.findall(r"<script>.*?</script>", html, re.S)
                   if "getElementById(\"filtros\")" in b]
        if not bloques:
            continue
        if cuerpo is None:
            cuerpo = bloques[0]
            (out / "filtros.js").write_text(
                cuerpo[len("<script>"):-len("</script>")].strip() + "\n", encoding="utf-8")
        if bloques[0] == cuerpo:
            pagina.write_text(
                html.replace(cuerpo, '<script src="filtros.js" defer></script>', 1),
                encoding="utf-8")


def _share_stylesheet(out: Path) -> None:
    import re
    paginas = sorted(out.glob("*.html"))
    hoja = None
    for pagina in paginas:
        html = pagina.read_text(encoding="utf-8")
        bloques = re.findall(r"<style>.*?</style>", html, re.S)
        if not bloques:
            continue
        if hoja is None:
            hoja = bloques[0]
            (out / "styles.css").write_text(
                hoja[len("<style>"):-len("</style>")].strip() + "\n", encoding="utf-8")
        if bloques[0] == hoja:
            html = html.replace(hoja, '<link rel="stylesheet" href="styles.css">', 1)
            pagina.write_text(html, encoding="utf-8")


def cmd_links(args) -> int:
    """Comprueba los enlaces que publica el informe. ES EL SEGUNDO COMANDO CON RED.

    Solo pide lo que puede estar muerto: la pestana de empleo de cada empresa
    (depende de que el slug sea correcto, y todos los del YAML estan propuestos
    sin verificar) y las URLs de oferta de terceros, que caducan en cuanto se
    cubre el puesto. Las busquedas no se comprueban: siempre responden.
    """
    import yaml
    from .links_check import BLOQUEADO, MUERTO, OK, aplicar, comprobar, recolectar

    settings = _settings(args)
    ruta = Path(args.data) if args.data else settings.config_dir / "curated_targets.yaml"
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    enlaces = recolectar(datos)
    if not enlaces:
        print("No hay enlaces que comprobar.")
        return 0

    ritmo = settings.run["min_delay_seconds"]
    print(f"Comprobando {len(enlaces)} enlaces, uno cada {ritmo}s. "
          f"Tardara unos {len(enlaces) * ritmo / 60:.0f} min.\n")
    informe = comprobar(enlaces, min_delay=ritmo,
                        timeout=settings.run["request_timeout_seconds"])

    ancho = max(len(r.enlace.ficha) for r in informe.resultados)
    for r in informe.resultados:
        marca = {OK: "ok", MUERTO: "MUERTO", BLOQUEADO: "--"}.get(r.veredicto, "REVISAR")
        print(f"  [{marca:>7}] {r.enlace.ficha:<{ancho}}  {r.codigo or '-'}  {r.enlace.url}")
        if r.nota:
            print(f"            {r.nota}")

    accionables = [r for r in informe.resultados if r.accionable]
    bloqueados = informe.por_veredicto(BLOQUEADO)
    print(f"\n{len(informe.por_veredicto(OK))} correctos, {len(accionables)} a corregir, "
          f"{len(bloqueados)} sin poder juzgar.")
    if bloqueados:
        print("Los bloqueados no dicen nada del enlace: repite mas tarde.")

    if args.write:
        cambios = aplicar(ruta, informe)
        if cambios:
            print(f"\n{ruta}:")
            for c in cambios:
                print(f"  - {c}")
            print("\nRegenera el sitio:  uv run rrhh-tools site --publico --out site-publico")
        else:
            print("\nNada que cambiar en el YAML.")
    elif accionables:
        print("Aplica el resultado al YAML con:  rrhh-tools links --check --write")
    return 0


def cmd_review(args) -> int:
    """Imprime la cola de revisión lista para pegar en config/decisions.yaml."""
    settings = _settings(args)
    run_id = cache.resolve_run(args.run)
    run = process(cache.load_raw(run_id), settings, run_id)
    if not run.review:
        print("# Nada pendiente de revisión en esta ejecución.")
        return 0
    print("# Pega estas líneas en config/decisions.yaml, bajo 'overrides:',")
    print("# cambiando el veredicto donde haga falta.\n")
    for company in run.review:
        print(f"  # {company.display_name} — {company.classification.label.value} "
              f"(confianza {company.classification.confidence})")
        for reason in company.classification.reasons:
            print(f"  #   {reason}")
        print(f"  - company_key: {company.key}")
        print("    verdict: END_CLIENT")
        print(f"    note: revisado a mano el {date.today().isoformat()}\n")
    return 0


def cmd_explain(args) -> int:
    settings = _settings(args)
    run_id = cache.resolve_run(args.run)
    run = process(cache.load_raw(run_id), settings, run_id)
    everything = run.targets + run.competition + run.intermediaries + run.review
    matches = [c for c in everything if args.company.lower() in c.key.lower()
               or args.company.lower() in c.display_name.lower()]
    if not matches:
        print(f"No hay ninguna empresa que coincida con {args.company!r}.", file=sys.stderr)
        return 1
    for company in matches:
        print(f"\n{company.display_name}  ({company.score} puntos, bloque "
              f"{company.classification.block.value})")
        print(f"  Clasificación: {company.classification.label.value} "
              f"(confianza {company.classification.confidence}, regla "
              f"{company.classification.rule_source})")
        for reason in company.classification.reasons:
            print(f"    · {reason}")
        print("  Desglose de la puntuación:")
        for component in company.components:
            print(f"    {component.label:34} {component.points:6.1f} / {component.weight:<4.0f} "
                  f"{component.explanation}")
        print("  Vacantes:")
        for job in company.jobs:
            print(f"    · {job.title_raw} — {job.location_raw} — {job.url}")
    return 0


# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rrhh-tools",
        description="Radar de ofertas junior de diseño en LinkedIn → cuentas objetivo para 2894.",
    )
    parser.add_argument("--config", default=None, help="directorio de configuración")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="comprueba que todo está listo antes de tocar LinkedIn")
    p.add_argument("--source", choices=["session", "guest"], default="session")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("search", help="descarga ofertas de LinkedIn (único comando con red)")
    p.add_argument("--source", choices=["session", "guest"], default="session")
    p.add_argument("--max-jobs", type=int, default=None)
    p.add_argument("--run-id", default=None)
    p.add_argument("--resume", action="store_true", help="omite lo ya visto en esta ejecución")
    p.add_argument("--record", action="store_true", help="guarda el HTML recibido como fixture")
    p.add_argument("--no-details", action="store_true",
                   help="no descarga la descripción de cada oferta (más rápido, clasifica peor)")
    p.add_argument("--dias", type=int, choices=[1, 7, 14, 30], default=None,
                   help="ventana de publicación; por defecto la del config (24h). "
                        "En la PRIMERA tirada usa 7 o más: con 24h casi no hay nada.")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("process", help="analiza una ejecución guardada")
    p.add_argument("--run", default="latest")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("report", help="genera el informe HTML")
    p.add_argument("--run", default="latest")
    p.add_argument("--out", default=None)
    p.add_argument("--orden", choices=["reciente", "prioridad"], default=None,
                   help="por defecto, la oferta publicada más reciente primero")
    p.add_argument("--source-label", default="LinkedIn")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("replay", help="pipeline completo contra fixtures, sin red")
    p.add_argument("--fixtures", default="tests/fixtures/http")
    p.add_argument("--out", default=None)
    p.add_argument("--query-id", default=None)
    p.add_argument("--max-jobs", type=int, default=None)
    p.add_argument("--today", default=None, help="fecha de referencia, para pruebas")
    p.add_argument("--orden", choices=["reciente", "prioridad"], default=None)
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("curated", help="renderiza la lista curada inicial de empresas")
    p.add_argument("--data", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--publico", action="store_true",
                   help="recorta el razonamiento comercial, para poder compartir el enlace")
    p.set_defaults(func=cmd_curated)

    p = sub.add_parser("site", help="monta el sitio estático con los informes")
    p.add_argument("--out", default=None)
    p.add_argument("--radar", default=None, help="informe del radar a incluir como muestra")
    p.add_argument("--publico", action="store_true",
                   help="recorta el razonamiento comercial, para poder compartir el enlace")
    p.set_defaults(func=cmd_site)

    p = sub.add_parser("links", help="comprueba los enlaces publicados (usa red)")
    p.add_argument("--check", action="store_true", default=True,
                   help="comprueba cada enlace (comportamiento por defecto)")
    p.add_argument("--write", action="store_true",
                   help="aplica el resultado al YAML: publica ofertas vivas, retira slugs malos")
    p.add_argument("--data", default=None)
    p.set_defaults(func=cmd_links)

    p = sub.add_parser("review", help="cola de revisión en formato decisions.yaml")
    p.add_argument("--run", default="latest")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("explain", help="desglose completo de una empresa")
    p.add_argument("--company", required=True)
    p.add_argument("--run", default="latest")
    p.set_defaults(func=cmd_explain)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"\nError de configuración:\n{exc}\n", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
