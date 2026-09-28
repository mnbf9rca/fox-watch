import argparse
import logging
import os
from pathlib import Path

from foxcam.classify import compare
from foxcam.pipeline import load_config, read_sidecar, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process recordings and compare Fox Watch labels")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "compare"):
        command = commands.add_parser(name)
        command.add_argument("--data", type=Path, default=Path(os.environ.get("DATA_DIR", "/data/foxcam")))
        if name == "run":
            command.add_argument("--night", help="Restrict processing and retention to YYYY-MM-DD")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        if args.command == "run":
            run(args.data, args.night)
            return 0
        config = load_config()
        rows, failed = [], False
        for path in sorted((args.data / "nights").glob("*/*.json")):
            try:
                rows.append(read_sidecar(path, config["PRIMARY_MODEL"]))
            except Exception as exc:
                logging.error("Sidecar %s: %s", path, type(exc).__name__)
                failed = True
        for model, (agreements, total) in sorted(compare(rows, config["PRIMARY_MODEL"]).items()):
            percent = f"{100 * agreements / total:.1f}%" if total else "n/a"
            print(f"{model}: {agreements}/{total} ({percent})")
        return int(failed)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        logging.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
