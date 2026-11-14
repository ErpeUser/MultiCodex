"""Capture every MultiCodex page, theme and supported window size."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def settle(app, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while app.jobs.pending and time.monotonic() < deadline:
        app.update()
        time.sleep(0.02)
    app.update_idletasks()
    app.update()
    if app.jobs.pending:
        raise RuntimeError("GUI background work did not settle")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Owned-window screenshots require Windows")

    from PIL import ImageGrab
    from multicodex.gui import MultiCodexApp, PAGES

    args.output.mkdir(parents=True, exist_ok=True)
    captures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="multicodex-screenshot-") as root:
        app = MultiCodexApp(data_dir=Path(root), auto_start=False)
        try:
            app.store.create("Pruefprofil")
            app._refresh()
            settle(app)
            for theme in ("dark", "light"):
                app._set_theme(theme)
                settle(app)
                for width, height in ((900, 640), (1180, 760)):
                    app.geometry(f"{width}x{height}")
                    app.update_idletasks()
                    for page in PAGES:
                        app._set_page(page)
                        app.update_idletasks()
                        app.update()
                        filename = f"{theme}-{width}x{height}-{page.lower()}.png"
                        target = args.output / filename
                        ImageGrab.grab(window=app.winfo_id()).save(target)
                        captures.append(filename)
        finally:
            app.closing = True
            app._shutdown()
    report = {
        "ready": len(captures) == 24,
        "count": len(captures),
        "themes": ["dark", "light"],
        "sizes": ["900x640", "1180x760"],
        "pages": list(PAGES),
        "files": captures,
        "scope": "temporary profile, owned MultiCodex window, no OAuth or saved account data",
    }
    (args.output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
