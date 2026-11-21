from __future__ import annotations

import sys

from gold_sentry.cli import main as cli_main


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) > 1:
        return cli_main()
    try:
        from gold_sentry.gui import run_gui
    except ImportError as exc:
        print(f"无法启动桌面界面: {exc}", file=sys.stderr)
        return 1
    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
