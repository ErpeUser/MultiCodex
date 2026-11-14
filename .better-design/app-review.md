# MultiCodex quota extension: bounded design review

Coverage: six existing main views inventoried in source; new quota/settings/history
widgets rendered in six fixture scenarios. Full-app visual audit incomplete.
Open findings: 0 known critical in reviewed widgets; 1 serious coverage gap,
1 moderate scope gap, 1 minor interaction issue. Unmeasured screens are not passed.

## Existing design and evidence

Preserved the repository's sea-glass palette and native stack. Better Design's
catalog suggested Retro LCD, Linear Quality, Interior, Telemetry and Playdesk;
none was installed over the existing design. Linear Quality is a relevant
reference, but a new purple/web system would conflict with the native palette.
Gain: stable native integration and honest data hierarchy. Cost: this is not a
pixel-identical Figma implementation or a full six-screen redesign.

Better Design UI principles and review rules were retrieved. The submitted quota
copy passed `check-comprehension` with zero findings (46 words, workspace surface).
That result is text-only: no accessibility, behavior or production approval.
The static awesome-design-md Linear study informed restrained hierarchy.
Public product images were inspected, not copied into the application:

- Linear, Behind the latest design refresh, 12 March 2026:
  https://linear.app/now/behind-the-latest-design-refresh
- Raycast, The new Raycast, 14 May 2026:
  https://www.raycast.com/blog/the-new-raycast

## Findings

1. **Serious / coverage gap (Derived):** complete CustomTkinter shell, Windows
   keyboard/DPI behavior and Figma comparison are unmeasured. A full redesign
   cannot be approved from isolated Tk fixtures. No invented pass/rule score.
2. **Moderate / scope gap (Derived):** Accounts and Instances retain their existing
   structure. The new searchable table is in Usage. The request's full-screen
   redesign and automatic profile management remain incomplete.
3. **Minor / interaction (Derived, quota_ui.py: refresh table):** a poll rebuilds
   table rows and reveals selection. On a large list this can disturb a user's
   manual scroll position. Selection survives, but scroll preservation needs work.

Fixed during review: clipped verbose table values were replaced with compact
consumed percentages; selected details show full context; disabled refresh has
readable neutral styling; history pagination/footer remain visible; initial
loading no longer implies zero stored accounts; percentages carry a consumed
basis (`rule/numbers-carry-a-unit`); actions name their result
(`rule/screen-passes-screenshot-test`).

## Coverage ledger

| Surface | Evidence | Not checked |
|---|---|---|
| Overview | Source integration and cached summary tests | Full rendered shell |
| Accounts/login/re-login | Source reviewed; original methods preserved | OAuth, native dialogs, redesign |
| Instances | Source reviewed, unchanged | Real desktop launch/focus/process behavior |
| Usage | Real Tk dark/light/small/empty renders, behavior tests | Full CTk parent, Windows DPI |
| Settings | New monitoring widget render and save callback tests | Existing full settings shell |
| Diagnostics | Source integration and redacted error boundary | Full rendered diagnosis view |
| Quota history dialog | Real Tk render, pagination tests | Windows accessibility |
| New/link/rename/confirmation dialogs | Existing code retained | Native render and keyboard review |

No Figma file was modified. Figma is installed, but this session exposes no Figma
actions. Better Design DOM dashboard/spacing checks are not measurements of a Tk
application and were not fabricated. No independent review agent was available;
source review and a separate skeptical pass were performed inline. The existing
full-repository/native release gates remain open.


## Continuation: queue and directory

Reviewed two added panels and the existing worker integration. Better Design
comprehension check returned zero findings for queue copy (text-only). Actual
Tk screenshots were inspected for activation dark/light/small and directory
dark/light; the panels retain existing tokens and explicit action labels.
No whole-app visual pass is claimed. The native Desktop binding, six original
views, installed Windows shell, DPI and Figma remain unmeasured this session.
Admin keys are masked and cleared on submission; no screenshot contains one.
