# Optional diagnostics preserved from PR #14

This independently based draft contains the non-baseline material split from
[PR #14](https://github.com/paulnord/epic-lfhcal-tbana/pull/14) at `0810773`.
The historical directory name is retained to preserve imports and commands;
these are **not baseline smoke tests**.

- [Strict raw-conversion diagnostics](RAW_CONVERSION.md): synthetic and acquired
  CAEN inputs, strict expected results, and known production failures. No decoder
  fixes or weakened assertions are included.
- [Acquired fixture provenance](fixtures/caen/README.md): exact original bytes,
  SHA256 hashes, extraction boundaries, and acquisition-quality limitations.
- [Historical plotting routines](../../NewStructure/tests/FIT_CURVE_TESTS.md):
  exploratory evidence and regression scripts tied to a superseded API, not a
  current passing plotting gate or physical-model validation.

Only four fixture-integrity tests and Python syntax compilation run in the
`Diagnostic fixture integrity` workflow. A green workflow means byte/record
integrity and syntax only; it does not run ROOT or either strict raw diagnostic,
validate the decoder, or establish plotting compatibility. The baseline runner,
ROOT payload/driver, 11 runner tests, and ROOT workflow belong to PR #14.
