"""Figma-derived UI tokens. This module owns palette, spacing and state values.

The native CustomTkinter/ttk surfaces consume semantic tokens from here so dark and
light themes keep the same hierarchy, focus treatment and status language.
"""
from __future__ import annotations

THEMES = {
    'dark': {
        'canvas': '#0D1114', 'rail': '#11161A', 'panel': '#182126',
        'text': '#F1F5F7', 'muted': '#9BAAB2', 'accent': '#8FD3C7',
        'accent_text': '#0D1114', 'border': '#273137', 'selected': '#26363B',
        'focus': '#8FD3C7', 'success': '#8FD3C7', 'warning': '#F2C879',
        'danger': '#F28B82', 'info': '#9CC9E8', 'disabled': '#65747A',
    },
    'light': {
        'canvas': '#F6F8F9', 'rail': '#F3F5F7', 'panel': '#FFFFFF',
        'text': '#162027', 'muted': '#64727A', 'accent': '#1E625B',
        'accent_text': '#FFFFFF', 'border': '#E4E8EB', 'selected': '#DDECE9',
        'focus': '#1E625B', 'success': '#1E625B', 'warning': '#8A5A00',
        'danger': '#A62B24', 'info': '#1F5D86', 'disabled': '#7B878D',
    },
}

# 4px base rhythm; use semantic names in view code instead of new literals.
SPACING = {'xs': 4, 'sm': 8, 'md': 12, 'lg': 16, 'xl': 24, 'xxl': 32}
CONTROL_HEIGHT = {'compact': 32, 'default': 36, 'primary': 40}
RADIUS_SCALE = {'control': 8, 'panel': 12, 'large': 16}
TYPE_SCALE = {'title': 26, 'section': 17, 'body': 13, 'caption': 12, 'micro': 11}
BREAKPOINTS = {
    'compact': 620, 'stack': 700, 'wide': 900,
    'compact_content': 640, 'stack_content': 700, 'wide_content': 900,
}
TEXT_SIZE = {
    'title': TYPE_SCALE['title'], 'section': TYPE_SCALE['section'],
    'body': TYPE_SCALE['body'], 'label': TYPE_SCALE['micro'], 'caption': 11,
}
STATUS_COLORS = {
    'success': {'dark': '#8FD3C7', 'light': '#1E625B'},
    'warning': {'dark': '#F2C879', 'light': '#8A5A00'},
    'danger': {'dark': '#F28B82', 'light': '#A62B24'},
    'info': {'dark': '#9CC9E8', 'light': '#1F5D86'},
}

def status_color(theme, status):
    """Return a semantic state color; state text remains mandatory in views."""
    return STATUS_COLORS.get(status, STATUS_COLORS['info'])[theme]
STATUS_TEXT = {
    'running': 'Läuft', 'idle': 'Bereit', 'unknown': 'Unbekannt',
    'invalidated': 'Ungültig', 'disabled': 'Deaktiviert',
    'live_verified': 'LIVE verifiziert', 'cached': 'Gespeichert', 'unverified': 'Nicht verifiziert',
}

PADDING = SPACING['xl']
RADIUS = RADIUS_SCALE['panel']
NAV_WIDTH = 220
