# Known limitations

## AI classification

- Grouping is probabilistic. Similar-looking products, abrupt camera-order
  changes, reflections, packaging-only shots, and missing views can reduce
  accuracy.
- Confidence scores are model estimates, not calibrated guarantees. Review
  `Needs_Review` and the CSV report before using results as a final catalog.
- Provider models can be renamed, retired, region-limited, or billing-limited.
  Use live model refresh after a `404`, access, or compatibility error.

## Input and workflow

- The source scanner currently processes JPG/JPEG files in the selected folder;
  it does not recursively scan nested folders or ingest RAW/HEIC/PNG files.
- Very high-resolution JPG/JPEG files are accepted up to a finite 200 MP safety
  ceiling. API payloads are downsampled to at most 1600 px on the longest edge;
  the original files are never resized or rewritten.
- Chronological capture order is important. Interleaved shoots of multiple
  products make grouping more ambiguous.
- The same output directory represents the same resumable operation. Select a
  new output directory when intentionally starting an independent run.
- Managed catalog outputs prefer zero-copy hardlinks, then symlinks, and finally
  real file copies when the filesystem or operating system does not permit links.
  A cross-volume run can therefore require additional free disk space.
- Internet access is required for cloud providers. Previously completed batches
  remain available while offline, but new AI analysis cannot continue.

## Desktop distribution

- Release binaries are not code-signed or notarized yet. Windows SmartScreen and
  macOS Gatekeeper may warn before first launch.
- Tkinter appearance can vary slightly by operating system, display scaling,
  font availability, and desktop theme.
- GUI smoke checks require a graphical desktop and cannot be completed in a
  headless test environment without a display server.

## Privacy and cost

- Selected photos are uploaded to the configured provider. Do not process
  sensitive images without reviewing that provider's current terms.
- Cost estimates depend on user-supplied rates and provider-reported usage; they
  are informational and may not match the final invoice.
- API-key rotation improves continuity but does not bypass provider account,
  project, model, regional, or billing restrictions.
