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
- [x] Validate produced artifacts on real desktop machines.
- [x] Validate the selected funded live provider with a non-sensitive two-image sample; OpenAI and Anthropic remain covered by automated integration tests until funded keys are available.
- [x] Publish signed-off `v3.1.0` release artifacts.
- [x] Publish `ai-product-photo-sorter` 3.1.0 to PyPI using Trusted Publishing.
- [x] Publish the backward-compatible `v3.1.1` maintenance release with the canonical `src/ai_product_photo_sorter/` package layout.

`v3.1.1` is the current stable patch release on GitHub Releases and PyPI. It
preserves the v3.1 command/configuration surface while moving the canonical
runtime into a maintainable `src/` package layout. Gemini passed the funded
end-to-end synthetic live sample. OpenAI and Anthropic integration paths remain
covered by automated request, key-pool, and compatibility tests, with optional
funded live verification available through the manual `live-provider-smoke`
workflow whenever usable API credit is available.

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