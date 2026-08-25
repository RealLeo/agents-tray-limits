# Repository Instructions

- Never create, enable, invoke, inspect, depend on, or otherwise use GitHub Actions in this repository.
- Do not add workflow files under `.github/workflows/`.
- Run validation and packaging locally with `make check`, `make pack`, `sha256sum`, and `unzip -t`.
- Publish GitHub Releases manually through the GitHub API or CLI only after the user explicitly authorizes that release.
- Do not make a push or tag contingent on a remote CI service; report the local verification results instead.
