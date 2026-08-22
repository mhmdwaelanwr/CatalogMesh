# Roadmap

This roadmap describes direction, not a guarantee or delivery schedule. Stable
releases are promoted only after automated builds and the manual checks in
`PRODUCTION_CHECKLIST.md` succeed.

## 3.1 — First stable desktop release

- [x] Shared GUI and CLI processing engine.
- [x] Gemini, OpenAI, and Anthropic provider pools.
- [x] One to four keys per provider with quota rotation.
- [x] Crash-safe SQLite resume and operation reports.
- [x] Live model discovery and multi-key compatibility checks.
- [x] Multilingual dark/light desktop dashboard.
- [x] Cross-platform brand and application icons.
- [x] Automated Linux, Windows, and macOS build pipeline.
- [ ] Validate produced artifacts on real desktop machines.
- [ ] Validate each provider with non-sensitive two-image samples.
- [ ] Publish signed-off `v3.1.0` release artifacts.

## 3.2 — Quality and workflow

- [ ] Thumbnail-based manual review and correction workflow.
- [ ] Configurable category profiles beyond electronics.
- [ ] Richer operation statistics and provider cost estimates.
- [ ] Export/import operation profiles without secrets.
- [ ] Improved accessibility, keyboard navigation, and high-DPI validation.

## 4.0 — Extensibility

- [ ] Provider plugin interface and custom OpenAI-compatible endpoints.
- [ ] Optional local vision-model adapter for fully offline processing.
- [ ] Catalog integrations and reusable export templates.
- [ ] Extension API for custom grouping and naming policies.

Contributions should start with an issue describing the user problem, expected
behavior, privacy impact, and a practical verification plan.
