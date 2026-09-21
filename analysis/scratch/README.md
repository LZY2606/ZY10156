# scratch experiments

Ad-hoc scripts used to trace the findings recorded in `../ANALYSIS.md`.
They are not part of the test suite; the pinned assertions live in
`tests/test_analysis_container_model.py`.

Run any of them from the repository root, e.g.:

    poetry run python analysis/scratch/exp4_edits.py

Do not run them from `/tmp` or another directory that shadows stdlib modules
(a stray `inspect.py` in the CWD breaks imports).
