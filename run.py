"""Desktop entrypoint with explicit, non-interactive verification modes."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description='MultiCodex desktop manager')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--self-check', action='store_true', help='Verify bundled runtime, not real accounts')
    group.add_argument('--gui-smoke', action='store_true', help='Render actual widgets using only a temporary test profile')
    parser.add_argument('--report', type=Path, help='Write a credential-free diagnostic JSON report')
    parser.add_argument('--screenshot-dir', type=Path, help='Capture the GUI smoke test; never use with real accounts')
    args = parser.parse_args(argv)
    if args.screenshot_dir and not args.gui_smoke:
        parser.error('--screenshot-dir requires --gui-smoke')
    if args.report and not (args.self_check or args.gui_smoke):
        parser.error('--report requires a verification mode')
    if args.self_check or args.gui_smoke:
        try:
            if args.self_check:
                from multicodex.health import check_runtime
                report = check_runtime()
            else:
                from multicodex.gui_check import check_gui
                report = check_gui(args.screenshot_dir)
        except Exception:
            report = {'ready': False, 'error': 'Verification could not run; dependencies or display unavailable'}
        text = json.dumps(report, ensure_ascii=True, indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(text+'\n', encoding='utf-8')
        if sys.stdout is not None:
            print(text)
        return 0 if report.get('ready') is True else 1
    try:
        from multicodex.gui import main as gui_main
        gui_main()
        return 0
    except Exception:
        message = 'MultiCodex konnte nicht gestartet werden. Abhaengigkeiten und lokale Berechtigungen pruefen.'
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        else:
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, message, 'MultiCodex', 0x10)
            except Exception:
                pass
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
