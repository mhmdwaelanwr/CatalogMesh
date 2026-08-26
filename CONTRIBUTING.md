# Contributing

1. Fork the repository and create a focused branch.
2. Do not commit `.env`, API keys, private images, catalogs, logs, or generated outputs.
3. Keep production code inside `src/ai_product_photo_sorter/`; the repository-root Python files and `src/*.py` compatibility modules must stay thin.
4. Keep GUI and CLI behavior consistent by routing processing through the shared core.
5. Add or update tests for behavioral changes.
6. Install the project in editable mode with `python -m pip install -e .`.
7. Run `python -m unittest discover -s tests -t . -v` and `python -m compileall -q src product_sorter.py product_sorter_gui.py set_data.py scripts`.
8. Open a pull request describing the problem, solution, tests, and supported platforms.

Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) before changing module boundaries or runtime paths.

For provider integrations, distinguish quota/rate-limit errors from invalid credentials, connectivity failures, and malformed requests. Never log credentials or image payloads.
