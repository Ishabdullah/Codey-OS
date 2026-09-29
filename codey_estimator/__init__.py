"""
codey_estimator -- vendored copy of the standalone Codey-Estimator library's
pure calculation/catalog package (`src/codey_estimator/`).

Vendored, not pip-installed, per the Phase B9.2 (Codey-Estimator Integration)
task decision -- restoricon_core.services.estimate_service is the only
in-repo consumer today. Stdlib-only (see the source repo's pyproject.toml:
`dependencies = []`), so no requirements.txt / install.sh change is needed
for this package itself.

Source: https://github.com/Ishabdullah/Codey-Estimator
Vendored commit: df0730f79f902835974101e6c05c18c8c20ce270 (2026-09-27)
Vendored on: 2026-09-29, as part of restoricon_core Phase B9.2.

Do not hand-edit files under this package to fix a bug -- fix it upstream in
Codey-Estimator and re-vendor (re-run the copy from a fresh clone), so this
copy never silently diverges from the source repo's own tests/history.
"""
