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
from .report.render import render_report
from .store import cache


def _settings(args):
    return load_settings(args.config)


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
def cmd_search(args) -> int:
    _load_env()
    settings = _settings(args)
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

    seen: set[str] = set()
    if args.resume:
        seen = set(cache.load_checkpoint(run_id).get("seen_ids", []))
        print(f"Reanudando: {len(seen)} ofertas ya vistas se omitirán.")

    try:
        if args.source == "session":
            from .sources import session
            records, labels = session.collect(queries, settings, max_jobs, seen, record_dir)
        else:
            from .sources import guest
            fetcher = ThrottledFetcher(
                min_delay=settings.run["min_delay_seconds"],
                jitter=settings.run["jitter_seconds"],
                timeout=settings.run["request_timeout_seconds"],
                max_retries=settings.run["max_retries_on_throttle"],
                record_dir=record_dir,
            )
            records, labels = guest.collect(fetcher, queries, settings, max_jobs, seen)
            diagnostics.pages_fetched = fetcher.pages_fetched
    except AuthWall as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 3
    except ThrottleStop as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        cache.save_checkpoint(run_id, {"seen_ids": sorted(seen)})
        return 4

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
    run = process(cache.load_raw(run_id), settings, run_id)
    html = render_report(run, settings.report["title"], source_label=args.source_label)
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
                  today=date.fromisoformat(args.today) if args.today else None)
    html = render_report(run, settings.report["title"], source_label="fixtures (sin red)")
    out = Path(args.out or "reports/replay.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    ok, message = run.reconcile()
    print(f"Replay: {len(records)} ofertas · reconciliación {'OK' if ok else 'FALLA'} — {message}")
    print(f"Informe escrito en {out}")
    return 0 if ok else 5


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

    p = sub.add_parser("search", help="descarga ofertas de LinkedIn (único comando con red)")
    p.add_argument("--source", choices=["session", "guest"], default="session")
    p.add_argument("--max-jobs", type=int, default=None)
    p.add_argument("--run-id", default=None)
    p.add_argument("--resume", action="store_true", help="omite lo ya visto en esta ejecución")
    p.add_argument("--record", action="store_true", help="guarda el HTML recibido como fixture")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("process", help="analiza una ejecución guardada")
    p.add_argument("--run", default="latest")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("report", help="genera el informe HTML")
    p.add_argument("--run", default="latest")
    p.add_argument("--out", default=None)
    p.add_argument("--source-label", default="LinkedIn")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("replay", help="pipeline completo contra fixtures, sin red")
    p.add_argument("--fixtures", default="tests/fixtures/http")
    p.add_argument("--out", default=None)
    p.add_argument("--query-id", default=None)
    p.add_argument("--max-jobs", type=int, default=None)
    p.add_argument("--today", default=None, help="fecha de referencia, para pruebas")
    p.set_defaults(func=cmd_replay)

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
