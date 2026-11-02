"""Command-line interface: ``mpplay <command>``."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .environment import Environment
from .planners import available_planners, get_planner, import_plugin_module
from .scenarios import GENERATORS, SCENARIOS, get_scenario


def _parse_kv(items: Sequence[str] | None) -> dict[str, str]:
    out = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"error: expected KEY=VALUE, got {item!r}")
        out[key.strip()] = value.strip()
    return out


def _load_environment(scenario: str | None, env_file: str | None) -> Environment:
    if env_file:
        return Environment.load(env_file)
    try:
        return get_scenario(scenario or "scattered")
    except KeyError as exc:
        raise SystemExit(f"error: {exc.args[0]}") from None


def _print_table(rows: list[list[str]], header: list[str]) -> None:
    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]
    line = "  ".join(h.ljust(w) for h, w in zip(header, widths, strict=True))
    print(line)
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths, strict=True)))


# --------------------------------------------------------------------------- commands


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app

    url = f"http://{args.host}:{args.port}/"
    print(f"Motion Planning Playground {__version__} running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level=args.log_level)
    return 0


def cmd_planners(args: argparse.Namespace) -> int:
    infos = [cls.info() for cls in available_planners()]
    if args.json:
        print(json.dumps(infos, indent=2))
        return 0
    rows = [[i["name"], i["label"], i["family"], i["summary"]] for i in infos]
    _print_table(rows, ["name", "label", "family", "summary"])
    if args.verbose:
        for info in infos:
            print(f"\n{info['label']} ({info['name']})")
            for p in info["params"]:
                extra = f" choices={p['choices']}" if "choices" in p else ""
                print(f"  --param {p['name']}={p['default']!s:10s} {p['help']}{extra}")
    return 0


def cmd_scenarios(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps([s.info() for s in SCENARIOS.values()], indent=2))
        return 0
    rows = []
    for name, scenario in SCENARIOS.items():
        env = scenario.build()
        rows.append([name, env.name, str(len(env.obstacles)), env.description[:70]])
    _print_table(rows, ["name", "title", "obstacles", "description"])
    gens = ", ".join(GENERATORS)
    print(f"\nGenerators (mpplay generate NAME): {gens}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    from .runner import run_planner

    env = _load_environment(args.scenario, args.env)
    try:
        get_planner(args.planner)
        result = run_planner(
            env,
            args.planner,
            _parse_kv(args.param),
            seed=args.seed,
            trace=bool(args.output or args.plot) and not args.no_trace,
            smoothing=args.smooth,
        )
    except (KeyError, ValueError) as exc:
        print(f"error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return 2
    status = "success" if result.success else f"failure: {result.message}"
    print(f"{result.label} on '{env.name}' (seed {args.seed}): {status}")
    for key, value in {**result.metrics, **result.stats}.items():
        print(f"  {key:28s} {value}")
    if args.output:
        payload = {"environment": env.to_dict(), "result": result.to_dict()}
        Path(args.output).write_text(json.dumps(payload) + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    if args.plot:
        from .viz import save_result_plot

        save_result_plot(env, result, args.plot)
        print(f"wrote {args.plot}")
    return 0 if result.success else 1


def cmd_benchmark(args: argparse.Namespace) -> int:
    from .benchmark import RunSpec, run_benchmark

    envs: list[Environment] = []
    names = args.scenario or ([] if args.env else ["scattered"])
    if "all" in names:
        names = list(SCENARIOS)
    for name in names:
        envs.append(_load_environment(name, None))
    envs.extend(Environment.load(f) for f in args.env or [])
    try:
        specs = [RunSpec.parse(s) for s in (args.planner or ["astar", "rrt", "rrt_star"])]
        for spec in specs:
            if args.smooth:
                spec.smoothing = True
            get_planner(spec.planner).Params.from_dict(spec.params)
    except (KeyError, ValueError) as exc:
        print(f"error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return 2

    def progress(done: int, total: int) -> None:
        if not args.quiet:
            print(f"\r  {done}/{total} runs", end="" if done < total else "\n", file=sys.stderr)

    result = run_benchmark(envs, specs, trials=args.trials, seed=args.seed, progress=progress)

    def fmt(entry: dict[str, Any], key: str) -> str:
        mean, std = entry.get(f"{key}_mean"), entry.get(f"{key}_std")
        return "-" if mean is None else f"{mean:.2f} ± {std:.2f}"

    rows = [
        [
            e["scenario"],
            e["run"],
            f"{e['success_rate'] * 100:.0f}%",
            fmt(e, "path_length"),
            fmt(e, "planning_time_ms"),
            fmt(e, "turning_deg"),
        ]
        for e in result.summary
    ]
    _print_table(rows, ["scenario", "run", "success", "length", "time [ms]", "turning [deg]"])
    if args.csv:
        Path(args.csv).write_text(result.rows_csv(), encoding="utf-8")
        print(f"wrote {args.csv}")
    if args.summary_csv:
        Path(args.summary_csv).write_text(result.summary_csv(), encoding="utf-8")
        print(f"wrote {args.summary_csv}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    env = _load_environment(args.scenario, None)
    return _write_env(env, args.output)


def cmd_generate(args: argparse.Namespace) -> int:
    gen = GENERATORS.get(args.generator)
    if gen is None:
        print(f"error: unknown generator {args.generator!r}; available: {', '.join(GENERATORS)}")
        return 2
    try:
        env = gen.generate(_parse_kv(args.param), args.seed)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return _write_env(env, args.output)


def _write_env(env: Environment, output: str | None) -> int:
    if output:
        env.save(output)
        print(f"wrote {output}")
    else:
        print(env.to_json())
    return 0


# --------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mpplay",
        description="Motion Planning Playground: explore, visualize and compare 2D planners.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--plugin",
        action="append",
        metavar="MODULE",
        help="import a module or .py file that registers extra planners (repeatable)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="start the interactive web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    p.add_argument("--log-level", default="warning", choices=["debug", "info", "warning", "error"])
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("planners", help="list available planners")
    p.add_argument("--json", action="store_true", help="print full descriptions as JSON")
    p.add_argument("-v", "--verbose", action="store_true", help="also list parameters")
    p.set_defaults(func=cmd_planners)

    p = sub.add_parser("scenarios", help="list built-in scenarios")
    p.add_argument("--json", action="store_true", help="print scenarios as JSON")
    p.set_defaults(func=cmd_scenarios)

    p = sub.add_parser("plan", help="run one planner on a scenario")
    src = p.add_mutually_exclusive_group()
    src.add_argument("-s", "--scenario", help=f"built-in scenario ({', '.join(SCENARIOS)})")
    src.add_argument("-e", "--env", help="environment JSON file")
    p.add_argument("-p", "--planner", default="astar", help="planner name (see 'mpplay planners')")
    p.add_argument("--param", action="append", metavar="KEY=VALUE", help="planner parameter")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--smooth", action="store_true", help="apply shortcut smoothing")
    p.add_argument("-o", "--output", help="write environment + result (with trace) as JSON")
    p.add_argument("--plot", help="save a figure (PNG/SVG/PDF; needs matplotlib)")
    p.add_argument("--no-trace", action="store_true", help="do not record the search trace")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("benchmark", help="compare planners over repeated trials")
    p.add_argument("-s", "--scenario", action="append", help="scenario name or 'all' (repeatable)")
    p.add_argument("-e", "--env", action="append", help="environment JSON file (repeatable)")
    p.add_argument(
        "-p",
        "--planner",
        action="append",
        metavar="SPEC",
        help="NAME or NAME:key=value,...,label=Text,smooth=true (repeatable)",
    )
    p.add_argument("-n", "--trials", type=int, default=10)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--smooth", action="store_true", help="apply shortcut smoothing to all runs")
    p.add_argument("--csv", help="write per-trial rows as CSV")
    p.add_argument("--summary-csv", help="write aggregated statistics as CSV")
    p.add_argument("-q", "--quiet", action="store_true", help="no progress output")
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser("export", help="write a built-in scenario as environment JSON")
    p.add_argument("scenario", choices=list(SCENARIOS))
    p.add_argument("-o", "--output", help="output file (default: stdout)")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("generate", help="generate a random environment as JSON")
    p.add_argument("generator", help=f"one of: {', '.join(GENERATORS)}")
    p.add_argument("--param", action="append", metavar="KEY=VALUE")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("-o", "--output", help="output file (default: stdout)")
    p.set_defaults(func=cmd_generate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    for plugin in args.plugin or []:
        import_plugin_module(plugin)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
