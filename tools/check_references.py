"""Check repository-local Markdown links after file relocations.

Only resolves local file targets; no network requests, file mutations, or credentials.
Usage: py -3.12 tools/check_references.py
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = (ROOT / "generated/project", ROOT / "plugins")

def broken_links() -> list[tuple[str, str]]:
    broken = []
    for base in FOLDERS:
        for file in base.rglob("*.md"):
            text = file.read_text(encoding="utf-8")
            # Strip fenced code blocks, which contain examples instead of links.
            text = re.sub(r"(?ms)^\s*`{3}[^\n]*\n.*?^\s*`{3}.*?$", "", text)
            for m in re.finditer(r"\]\(([^)]+)\)", text):
                value = m.group(1).strip()
                if value.startswith("<") and value.endswith(">"):
                    value = value[1:-1]
                parsed = urlsplit(value)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                if parsed.path.startswith("/") or "%" in parsed.path and "%00" in parsed.path.lower():
                    continue
                filename = unquote(parsed.path)
                target = file.parent / filename
                if not target.exists():
                    broken.append((file.relative_to(ROOT).as_posix(), value))
    return broken

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    missing = broken_links()
    if not args.quiet:
        for source, target in missing:
            print(f"BROKEN_LINK {source}: {target}")
        print("BROKEN_LINK_COUNT", len(missing))
    return 1 if missing else 0

if __name__ == "__main__":
    raise SystemExit(main())
