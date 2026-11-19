# MultiCodex

MultiCodex is a native Windows workspace for managing separate Codex desktop profiles and their non-secret usage views. It is an independent project and is not an official OpenAI product.

The source tree is public. Local credentials, profiles, build output, evidence, caches and migration backups are excluded by the repository rules.

- Project documentation: [generated/project/docs/README.md](generated/project/docs/README.md)
- Repository layout: [generated/project/docs/LAYOUT.md](generated/project/docs/LAYOUT.md)
- Development workflow: [AGENTS.md](AGENTS.md)
- Security notes: [generated/project/docs/security.md](generated/project/docs/security.md)

Run the layout and source-reference checks before committing:

```powershell
py -3.12 tools/check_generated_layout.py
py -3.12 tools/check_references.py
```
