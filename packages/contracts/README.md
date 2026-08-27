# Public contracts

`openapi.json` and files under `schemas/` are authoritative. Run
`uv run python scripts/generate_contracts.py` after a reviewed change and
`uv run python scripts/generate_contracts.py --check` in CI. Never hand-edit
files under `generated/` or Android/Web generated paths.

The frozen Agent tool registry is generated from the runtime Pydantic models:

```powershell
uv run python scripts/generate_agent_artifacts.py --check
```
