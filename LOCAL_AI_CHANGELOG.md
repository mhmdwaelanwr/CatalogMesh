# Local-first implementation scope

This development slice introduces Ollama as a first-class local vision provider
without changing the existing cloud provider contracts.

Implemented in this slice:

- Ollama `/api/chat` multimodal inference with JSON output.
- Installed-model discovery through `/api/tags` and vision capability checks via
  `/api/show`.
- Local-only and local-first provider chains.
- CLI flags for local mode, model, endpoint, keep-alive, and timeout.
- Desktop Ollama panel inside Models & API keys.
- Environment Center and setup-wizard persistence for local settings.
- Offline operation when Ollama is part of the provider chain.
- Bounded encoded-image LRU cache shared by local and cloud paths.
- Existing Benchmark Center timing and token accounting for Ollama calls.
- Regression tests for discovery, inference payloads, CLI wiring, cache reuse,
  local credential-validation behavior, and environment persistence.

Follow-up work remains tracked in `ROADMAP.md`, including hardware-aware model
recommendations, adaptive local batching, embedding/OCR pre-clustering, richer
local performance metrics, and continued desktop visual refinement.
