# MultiCodex design system — working source of truth

Design: [editable MultiCodex frames](https://www.figma.com/design/iKeNG6k7TfG5U98yfqKFxI). Dark frame `1:2`; light frame was created alongside it. This design is an implementation reference, **not a screenshot of the running Windows build**.

## Identity and purpose

Audience: Windows developers managing isolated Codex desktop profiles and a separate Codex multi-auth account pool. The primary task is to identify which instance is running and safely launch or stop **only** that instance. Managed profile-local login slots must be visibly distinct from the read-only global pool; safe pool adoption remains incomplete.

Visual signature: operational console rail with high-contrast profile state and a restrained sea-glass accent. Avoid fake health statistics or colorful status tiles without evidence. Figma is the source for the two color palettes; the Python runtime token module (`multicodex/ui_tokens.py`) owns their application values.

## Colors

| Meaning | Dark | Light |
| --- | --- | --- |
| Canvas | `#0D1114` | `#F6F8F9` |
| Sidebar | `#11161A` | `#F3F5F7` |
| Raised panel | `#182126` | `#FFFFFF` |
| Primary text | `#F1F5F7` | `#162027` |
| Muted text | `#9BAAB2` | `#64727A` |
| Accent | `#8FD3C7` | `#1E625B` |
| Subtle divider | `#273137` | `#E4E8EB` |

Typography: Figma's Inter Regular/Medium/Semi Bold at 26px / 16px / 13px; Windows CustomTkinter currently uses Segoe UI as locally available fallback. The font mismatch is not visually validated on Windows. Shell target: 1280 × 760 with a 220px sidebar, 36–40px content inset, 12px panel radius, 8px primary button radius, and density appropriate to account tables. Light and dark themes expose the same actions and language.

## Component/interaction contracts

Selected navigation uses a low-contrast filled surface, not a border. The main action is solid. Running, Idle, Unknown, Invalidated, and Disabled must include text instead of color alone. Remote requests run in worker threads and marshal completion to the GUI thread via a queue. No hidden real data or fabricated metrics are displayed.

## Recovery implementation decision

The existing rail, palette and native toolkit are retained. Labels are German; controls wrap into two columns at compact widths. Summary figures are backed by local metadata/process snapshots, not the design's sample accounts. Identity labels say assigned/saved, not live-authenticated. The current layout has not been rendered in this environment because CustomTkinter is unavailable; no pixel-fidelity or DPI claim is made.

## Quota history extension - development patch, 14 November 2026

The Usage screen gains a native Tk/ttk table inside the existing CustomTkinter
shell, not a replacement application or web framework. It keeps the existing
palette, German copy and keyboard-accessible text actions. Counts, records and
selected-account detail are visible together; older observations are paginated
in a separate history window. Progress bars mean **consumed**, never remaining.
Unknown values have no invented bar. Expired historical resets retain the old
consumption and explicitly require verification.

The initial settings extension enabled only read-only quota monitoring. The
following paragraph records that first slice; see the continuation below. Automatic
profile activation and workspace administration are visibly unavailable, not
silently simulated. Initial loading is not rendered as an empty account list.

Better Design principles and a copy check informed hierarchy and labels;
awesome-design-md's static Linear study and public Linear/Raycast product
screenshots informed density, subdued chrome and explicit actions. No catalog
system, brand assets, fonts or React components were installed. This keeps the
native stack and existing identity but does not reproduce Figma pixel-for-pixel.

Six real Linux/Tk fixture renders cover the new widgets. The full CustomTkinter
shell, all existing screens, Figma editing and Windows/DPI acceptance remain
unverified. See [implementation](docs/quota-implementation.md),
[verification](docs/quota-verification.md) and
[design review](.better-design/app-review.md).


## Explicit profile starts and workspace visibility

The Usage page gains an exact-account start queue below quota history. Keep its
scope visible: no automatic account rotation, no closing existing windows, and
waiting means unconfirmed capacity. Selection, pending, paused, recovery and
verified-process-binding states use text, not color alone. Administrative member
visibility belongs to Diagnostics and is read-only; the key input is masked and
cleared after submission. No invented role/seat fields or implied authorization.
Reuse current typography, sea-glass accent and dark/light surfaces. Reuse
QuotaSettingsPanel and update its capability note at the integration boundary.
Real Linux Tk component captures cover both themes and a narrow queue layout.
They do not certify the complete shell, Windows DPI, native focus or accessibility.
