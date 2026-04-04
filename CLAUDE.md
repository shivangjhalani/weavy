# Arakne

The complete idea lives in `markdowns/Memory-v5.md`

Build plan lives in `markdowns/build-plan/`. Always consult the relevant
phase doc before implementing. Design rules are in `00-overview.md`.

- Sync-only, strict Pydantic, explicit failures, no API layer in v1
- Environment is managed by `devenv.nix`
- FalkorDB graph store, LiteLLM for model calls
- Use `uv` for deps, `ruff` for formatting, `pytest` for tests
