## Summary

Describe the change in a few clear sentences.

## Why

What user or maintenance problem does this solve?

## Risk / privacy

- Does this change touch API keys, provider requests, local files, databases, packaging, or release publishing?
- Note any privacy, billing, migration, or backward-compatibility impact.

## Verification

- [ ] `python -m unittest discover -v` passes.
- [ ] Relevant platform/build checks pass where applicable.
- [ ] No credentials, private images, generated outputs, or local runtime state are included.
- [ ] GUI and CLI behavior remain consistent where applicable.
- [ ] Documentation and changelog were updated where applicable.
- [ ] Release/version metadata remains consistent if packaging or publishing changed.

## Screenshots / logs

Add non-sensitive screenshots or logs when they materially help review. Redact credentials and private paths.
