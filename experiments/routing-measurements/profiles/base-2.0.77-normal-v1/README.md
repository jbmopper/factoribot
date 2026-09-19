# Factorio 2.0.77 validation target

User selected 2.0.77 on 2026-09-12. The installed macOS ARM Steam executable
reports build 84539. This directory pins a fresh base-only prototype export,
not measured throughput. The routing runtime now consumes the corresponding
2.0.77 dump and generated packaged extract.

The export used `--config` and `--mod-directory` pointing to an isolated temporary
workspace. Its mod-list enabled only base; logs confirm base 2.0.77 and built-in
core. No existing save, global mod configuration, or previous data dump changed.
The temporary workspace was removed after retaining these artifacts.

- `mod-list.json` and `export.log`: actual export environment and execution.
- `raw_prototype_slice.json`: selected raw fields from the new dump.
- `prototypes.json` and `manifest.json`: parsed extract and identified provenance.
- `comparison.json`: differences against the previous unidentified/modded slice.
- Full dump retained locally at `data/data-raw-dump-2.0.77-base.json` (gitignored),
  SHA-256 `be65dc3615d5939e522b00543b2925a02cfa890dbc9c00882dfe1c4629670f60`.

All overlapping selected prototype fields match the prior export. The old
`ee-super-substation` is absent, as expected for a base-only environment. This
comparison does not prove equal engine behavior; it covers selected prototype
fields only. Historical 2.0.76 documentation references retain their real version.

The completed migration preserves the old pilot's unsupported mod entities and
updates version-bound request/graph identities and tests together. New task-23
captures are explicitly bound to 2.0.77. Historical mechanics records keep their
original 2.0.76 profile and remain incompatible with the current runtime until a
reviewed, compatible observation supersedes them.
