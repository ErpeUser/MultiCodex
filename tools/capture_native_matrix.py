"""Capture six real source-GUI views on a Windows display at its measured DPI.

Run once at each OS scale: 100, 125, 150 and 200 percent. Changing Tk's internal
scaling is deliberately NOT a substitute for changing Windows display scaling.
Only temporary fixture profiles and the owned application window are captured.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.native_evidence import (DPI_PERCENT, EvidenceError, _safe_path, capture_plan,
                                   file_hash, source_identity, write_report)


def _window_dpi(window: int) -> int:
    import ctypes
    from ctypes import wintypes
    get_dpi = ctypes.windll.user32.GetDpiForWindow
    get_dpi.argtypes = [wintypes.HWND]
    get_dpi.restype = wintypes.UINT
    dpi = int(get_dpi(window))
    if dpi <= 0:
        raise EvidenceError('DPI_UNAVAILABLE')
    return dpi


def capture(root: Path, output: Path, setup: Path, commit: str, percent: int) -> dict:
    if sys.platform != 'win32':
        raise EvidenceError('WINDOWS_REQUIRED')
    if type(percent) is not int or percent not in DPI_PERCENT:
        raise EvidenceError('INVALID_DPI')
    if source_identity(root) != commit:
        raise EvidenceError('SOURCE_MISMATCH')
    output = _safe_path(output)
    if output.exists():
        raise EvidenceError('OUTPUT_EXISTS')
    setup_hash = file_hash(setup)
    from PIL import ImageGrab
    from multicodex.gui import MultiCodexApp, PAGES
    from tools.capture_gui_screenshots import settle
    plan = capture_plan()
    if set(PAGES) != {item['page'] for item in plan}:
        raise EvidenceError('PAGE_COVERAGE_CHANGED')
    rows = []
    with tempfile.TemporaryDirectory(prefix='multicodex-native-fixture-') as temp:
        app = MultiCodexApp(data_dir=Path(temp), auto_start=False)
        try:
            app.update_idletasks()
            expected_dpi = percent * 96 // 100
            if _window_dpi(app.winfo_id()) != expected_dpi:
                raise EvidenceError('WINDOWS_DISPLAY_SCALE_MISMATCH')
            output.mkdir(parents=True, exist_ok=False)
            app.store.create('Pruefprofil')
            app._refresh()
            settle(app)
            last_theme = None
            for item in plan:
                if last_theme != item['theme']:
                    app._set_theme(item['theme'])
                    settle(app)
                    last_theme = item['theme']
                width, height = item['window_size']
                app.geometry(f'{width}x{height}')
                app._set_page(item['page'])
                settle(app)
                dpi = _window_dpi(app.winfo_id())
                if dpi != expected_dpi:
                    raise EvidenceError('DPI_CHANGED_DURING_CAPTURE')
                path = output / item['file']
                # Deliberately no desktop/bounding-box fallback.
                image = ImageGrab.grab(window=app.winfo_id())
                image.save(path, format='PNG')
                rows.append({**item, 'native_dpi': dpi, 'image_size': list(image.size),
                             'sha256': file_hash(path)})
        finally:
            app.closing = True
            app._shutdown()
    if source_identity(root) != commit or file_hash(setup) != setup_hash:
        raise EvidenceError('BUILD_CHANGED_DURING_CAPTURE')
    manifest = {'schema': 1, 'source_commit': commit, 'setup_sha256': setup_hash,
                'platform': 'win32', 'capture_kind': 'owned-window', 'dpi_percent': percent,
                'files': rows, 'scope': 'source GUI, temporary fixture, no OAuth or real account data'}
    write_report(output / 'manifest.json', manifest)
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--setup', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--dpi', type=int, choices=DPI_PERCENT, required=True)
    args = parser.parse_args(argv)
    try:
        capture(Path(__file__).resolve().parents[1], args.output, args.setup, args.commit, args.dpi)
    except Exception:
        # Partial images remain for diagnosis, but no successful manifest is written.
        print('Native capture not completed. Check Windows display scale, clean source, dependencies and a new output path.')
        return 1
    print('24 owned-window source-GUI captures saved. Native account acceptance is still required.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
