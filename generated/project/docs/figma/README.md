# Local editable Figma reference

This development plugin creates a **new** reference page in the open Figma Design
file. It contains Overview, Accounts, Instances, Usage, Diagnostics and Settings
in both dark and light: twelve editable screens. Text and auto-layout frames are
real layers, not screenshots. Every screen identifies its synthetic example data
and explicitly says that it is not runtime evidence.

The palette, navigation width and panel radius come from
`multicodex/ui_tokens.py` at package-build time. The existing application remains
Python/CustomTkinter; this plugin does not replace it, change real accounts, read
credentials, or claim pixel-identical reproduction. It does not publish a Figma
library or create Code Connect bindings.

## Build and run

Use Figma Desktop to create a development plugin and copy the **Figma-assigned
numeric ID** from its manifest. The builder validates its shape, not ownership or
registration; do not substitute the synthetic ID used by tests.

From the MultiCodex repository, build a new output directory:

```powershell
python tools/build_figma_plugin.py --plugin-id YOUR_FIGMA_ASSIGNED_NUMERIC_ID --output generated/runtime/output/figma-reference
python tools/build_figma_plugin.py --plugin-id YOUR_FIGMA_ASSIGNED_NUMERIC_ID --output generated/runtime/output/figma-reference --check
```

Replace the uppercase placeholder with the numeric ID before executing. Import
`generated/runtime/output/figma-reference/manifest.json` through Figma's development-plugin menu,
open the intended Design file and run the plugin. The package needs no npm
installation or compilation step. Python creates the package; Node is used only
for tests. Fonts are never bundled or redistributed.

Inter Regular must be available in Figma. The plugin discovers an available Inter
emphasis style and awaits font loading before creating the page. Missing fonts
stop the run before changing the document. After running, inspect all twelve
screens in Figma for wrapping, spacing and editability: the automated tests do
not emulate Figma's real text measurement or layout engine.

## Repeat runs and failures

Each successful run creates a separately named page. Existing frames and edits
are never overwritten. Re-running the generator is additive, not an automatic
update of the earlier reference. On an error it attempts to restore the previous
page and remove only the new partial page. A failed cleanup can leave a new
partial page; the plugin reports failure rather than pretending that cleanup or
generation succeeded.

The package builder also refuses an existing output directory. Keep any edits,
then choose a new output directory for a rebuild. `--check` rejects changed
source tokens, modified generated code, unexpected files and linked paths.

The package contains exactly `manifest.json`, `code.js` and `package-meta.json`.
The manifest denies network access. Source/token/code hashes in the metadata are
consistency checks, not a signature or evidence that the plugin ran in Figma.
No credentials, personal profiles, screenshots, font files or provider responses
are included.

## Tests

```powershell
python -m unittest discover -s tests -p test_figma_package.py -v
node --test tests/figma/renderer.test.cjs
```

The Python suite builds real packages and invokes the real packaging CLI. It also
runs the Node suite when Node is present, so the repository's existing Python test
command discovers the plugin tests without a separate CI dependency. The Node
suite uses an explicitly synthetic Figma API double to check layer construction,
font ordering, input validation, repeat-run preservation and failure cleanup.
It is not a live Figma render. See `generated/project/docs/delivery-tools-verification.md` for the
executed checks and remaining acceptance requirements.

## Official API references

- https://developers.figma.com/docs/plugins/manifest/
- https://developers.figma.com/docs/plugins/plugin-quickstart-guide/
- https://help.figma.com/hc/en-us/articles/360042786733-Create-a-classic-plugin-for-development

The renderer uses the standard public Plugin API, not harness-specific shortcuts.
