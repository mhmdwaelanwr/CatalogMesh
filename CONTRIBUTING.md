# Contributing

1. Fork the repository and create a focused branch.
2. Do not commit `.env`, API keys, private images, catalogs, logs, or generated outputs.
3. Keep the shared engine in `sorter_core.py`; GUI and CLI behavior should remain consistent.
4. Add or update tests for behavioral changes.
5. Run `python -m unittest discover -v` and `python -m py_compile *.py`.
6. Open a pull request describing the problem, solution, tests, and supported platforms.

For provider integrations, distinguish quota/rate-limit errors from invalid credentials, connectivity failures, and malformed requests. Never log credentials or image payloads.
