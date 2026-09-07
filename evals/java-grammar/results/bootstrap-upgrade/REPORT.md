# Existing bootstrap runtime candidate adoption

The source/ZIP bootstrap previously ignored a newly supplied wheelhouse when its existing pinned runtime passed doctor. Even a dependency installation without upgrade could retain upstream 0.23.5 because it satisfies the public pin. This prevented adoption of the annotated-varargs fix in existing environments.

Bootstrap now fingerprints local wheel filenames and bytes, considers changed candidates during readiness, and requests upgrade/reinstallation when explicit candidates change. Unchanged healthy runs skip pip. A failed install or candidate mutation does not record successful candidate adoption. Candidate files are checked again before saving readiness. These checks do not make installation transactional; failures may leave partially changed dependencies for retry.

[Local real-package receipt](local.json): macOS arm64, Python 3.11.16, an initially fresh target followed by two installs into the same runtime. Version sequence is `0.23.5 → 0.23.5+columbus.1 → 0.23.5+columbus.1`; unchanged annotated-varargs source has `partial=true → false → false`. Pip runs on the first two operations and skips the third. The probe uses the actual install.py/bootstrap path and reads its indexed parse result in the installed interpreter. Logs are retained locally under `.omx/observations/bootstrap-upgrade/logs`; hashes are in the receipt.

All 50 root tests pass, including replacement of same-name candidate bytes, failed-install retry, and unchanged-run behavior. The initial real-package probe incorrectly parsed mixed pip/installer stdout as one JSON value; after collecting runtime state separately, the full three-step probe passed. An initial test invocation used unsupported system Python; the reported passing suite uses the supported project environment.

Reproduce: `.venv/bin/python evals/java-grammar/verify_bootstrap_upgrade.py WHEELHOUSE OUTPUT.json`. The experimental grammar workflow now runs this probe in all six platform/Python combinations; hosted results for this change are pending.

This fixes explicit wheelhouse adoption in the source/ZIP bootstrap. It does not publish the candidate, make it a default public dependency, implement candidate switching in an already-ready standalone get-columbus.py version, or guarantee downgrade when the wheelhouse is removed. Default release integration and broader relationship precision remain open, as does the actual-token savings goal.
