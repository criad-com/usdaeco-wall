# Verification status

For **v0.2.5**, see [public re-pin verification](public-repin-verification.md).
The measurements below are historical.

Version **0.2.1** (historical) uses toolchain **v0.3.1**. Version **0.2.2**
passes **86 checks, 0 failed** with toolchain **v0.3.5**; see the
[README](../README.md#status). The historical integrated command
`check.py --report out/check.json` reports **86 checks, 2 failed** after adopting MIT.
The publication passed **86 checks, 0 failed** before that licence change.
The [machine-readable report](check-results.json) retains every raw result.
The [README](../README.md#build-and-check) provides the exact pinned setup.

| Acceptance row | Verified result |
|---|---|
| Inherited acceptance floor | 46 checks retained, all pass |
| All behavioral checks | 58 checks, 0 failed |
| Raw structure lint | 26/28 pass; S01 and S25 fail on the MIT licence; S27/S28 pass |
| Source-run pytest | 24 passed |
| Schema compared with v0.1.2 using Sdf | 27 properties unchanged across both APIs |
| Python validator discovery | Wall 6/6; core 8/8 loaded through UsdValidation |
| Core validator execution | Seeded missing identity detected as an error |
| Published clash example | pinned v0.4.1; expected findings unchanged |
| Promoted walls / equivalent build-up types | 92 / 3 |
| L01 wall axes | 19 |
| Recorded joins / openings / selected findings | 0 / 0 / 0 |
| Published meshes preserved | 3,015; topology and world transforms unchanged |
| Extent guides excluded | 35 |
| Committed result inventory | 8 files, 2,548,686 bytes of 10,000,000 allowed |
| Standalone crate | 1,684,649 bytes; 12,375 prims |
| Archived own layers | 5 USDA files; largest 649,080 bytes of 2,000,000 allowed |
| Vanilla render | 1280 × 800; 80,491 bytes of 400,000 allowed; non-uniform |
| Guide-inclusive review render | 1280 × 800; 80,508 bytes; non-uniform |
| S27 | Relocated crate opens plugin-free; 0 composition errors; complete fallbacks |
| Stale-result comparison | Fresh run matches committed crate normalization and all text layers |
| S28 | Independent stock Embree render with no family plugins passes |
| usdGenSchema validation | Clean; installed compiler compatibility checked |
| Term sweep | S25 flags LICENSE:3 only; result layers are clean |
| Nix flake check | One attempt with --offline; public axis v0.1.0 input reports HTTP 404; not proven |
| Native regeneration / live round trips / numerical clash | NOT RUN |

## Deviations

- MIT licensing and its requested copyright notice conflict with toolchain
  v0.3.1: S01 requires Apache-2.0 text; S25 rejects the copyright name at
  `LICENSE:3`. These raw failures are retained, with no lint bypass.
  This historical licence-lint blocker was resolved by later shared toolchain
  releases; see [v0.2.4 verification](public-name-verification.md).

- Nix input resolution failed before a build. No Nix build or platform
  compatibility claim is made, and no retry was attempted.
- The available data-centre and axis checkouts had advanced beyond the
  declared pins. Read-only tag archives under ignored `out/pinned/` supplied
  data-centre v0.4.1 and axis v0.1.0; no sibling checkout was modified or built.
  The documented extraction locations also preserve the source-relative
  path in the archived driver layer. The flattened crate is independent
  of those locations and was opened after relocation.
- The shared harness renders its default purposes before the runner's
  existing guide-inclusive review render. The independently generated
  vanilla proof uses the S28 purposes `proxy,render`.
- The example retains the published tessellation and measured wall census.
  Three equivalent single-layer sections do not establish original material
  construction, and absent join/opening records remain absent. Native
  regeneration, live round trips and numerical clash comparison remain
  outside this publication.

The earlier opening class/namespace lint blocker is resolved by the
library's declared ownership and the shared toolchain rules. No local
lint exceptions are used.
