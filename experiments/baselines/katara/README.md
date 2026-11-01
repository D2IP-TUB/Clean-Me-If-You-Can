# KATARA

Python port of the domain-KB path in `SimplifiedPatternDiscovery` (Chu et al., via the REDS Java KATARA). The harness runner is `experiments/harness/run_katara.py`.

Place the domain knowledge base at `dominSpecific/` (files named `*.type.txt` and `*.rel.txt`). The first load is cached as `.katara_kb_cache.pkl` in this directory.

The REDS estimator and its other cleaning-tool wrappers are not included. This port is under the Apache License 2.0 (`LICENSE.md`).
