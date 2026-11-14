"""Real-widget installation probe, isolated from all saved user accounts."""
from __future__ import annotations
import tempfile
import time
import sys
from pathlib import Path


def check_gui(screenshot_dir: Path | None = None) -> dict:
    from .gui import MultiCodexApp, PAGES
    errors, screens = [], []
    with tempfile.TemporaryDirectory(prefix='multicodex-gui-check-') as root:
        app = MultiCodexApp(data_dir=Path(root), auto_start=False)
        app.report_callback_exception = lambda *_: errors.append('Tk callback failed')
        try:
            app.store.create('Pruefprofil')
            app._refresh()
            def settle():
                deadline = time.monotonic() + 8
                while app.jobs.pending and time.monotonic() < deadline:
                    app.update()
                    time.sleep(.02)
                app.update()
                if app.jobs.pending or errors:
                    raise RuntimeError('GUI verification did not settle')
            settle()
            for theme in ('dark', 'light'):
                app._set_theme(theme)
                settle()
                for page in PAGES:
                    app._set_page(page)
                    app.update()
                    if not app.page_frame.winfo_children() or errors:
                        raise RuntimeError('Page did not render')
                    if not app.sign_in_button.winfo_ismapped():
                        raise RuntimeError('Sign-in entry is not visible')
                    screens.append(theme + '/' + page)
                for width, height in ((900, 640), (1180, 760)):
                    app.geometry(f'{width}x{height}')
                    app._set_page('Overview')
                    app.update()
                    if app.header_title.winfo_rootx() < app.rail.winfo_rootx() + app.rail.winfo_width():
                        raise RuntimeError('Header overlaps navigation')
                    if app.progress.winfo_ismapped() or app.cancel_button.winfo_ismapped():
                        raise RuntimeError('Idle GUI falsely displays sign-in activity')
                if screenshot_dir:
                    from PIL import ImageGrab
                    screenshot_dir.mkdir(parents=True, exist_ok=True)
                    # Capture only this owned test window. Desktop bounding-box
                    # capture can leak unrelated foreground windows into evidence.
                    if sys.platform != 'win32':
                        raise RuntimeError('Owned-window screenshots require Windows')
                    ImageGrab.grab(window=app.winfo_id()).save(screenshot_dir/f'gui-smoke-{theme}.png')
        finally:
            app.closing = True
            app._shutdown()
    return {'ready': True, 'screens': screens, 'sizes': ['900x640', '1180x760'],
            'scope': 'actual widgets, temporary profile, no OAuth or desktop-app integration'}
