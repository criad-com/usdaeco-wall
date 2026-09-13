# Public re-pin verification

Version **0.2.5** applies the six requested release tags and records each
checked source revision in [dependencies.json](../dependencies.json).
[The machine-readable receipt](public-repin-verification.json) contains the
full gate, source/result hashes, public tag probes and fresh-render comparisons.

| Acceptance | Measured result |
|---|---|
| Direct family pins | 6/6 requested tags; 6/6 checked source revisions match the release tags |
| Library requirement ranges | Unchanged; all 3 schema dependency versions fit |
| Package versions | library.json, pyproject.toml, source package and resource descriptor: 0.2.5 |
| Full source gate | 87 checks, 0 failed, 0 not run |
| Behavioral checks | 58 checks, 0 failed |
| Structure with toolchain v0.3.10 | 29 checks, 0 failed, including S05 and S25 |
| Source-run pytest | 24 passed; no installed package or setuptools required |
| Final publication sweep | 70 files checked, 0 findings, including decoded USD crates |
| Pin and whitespace sweep | 0 old public-org refs; 0 family commit-hash URLs; git diff --check clean |
| UsdValidation | 6 wall validators and 8 core validators; seeded identity defect detected |
| Schema source and generated schema | Both byte-identical to v0.2.4; compiler validation passes |
| Published source and findings | Source manifest and all 3 source layers unchanged; findings byte-identical |
| Wall coverage | 92 walls, 3 equivalent single-layer types, 19 L01 axes, 0 selected findings |
| Geometry comparison to v0.2.4 | 3,015 meshes, 19 curves and 12,299 world transforms unchanged |
| Archived own layers | 2/5 byte-identical; 3/5 differ only in producer strings |
| Flattened crate | 1,685,119 bytes; 12,375 prims; only 19 axis stamps change |
| Published result | 8 files, 2,549,113 bytes; all 3 committed PNGs retained byte-for-byte |
| S27 / S28 / S29 | Relocated plugin-free composition, independent stock render and portable sources pass |
| Public availability | 2/6 direct tags confirmed; 4/6 public tag pages return HTTP 404 |
| Nested public tags | aeco-toolchain v0.4.0 and core fixture v0.9.2 confirmed |
| Nix | 1 offline attempt; current-platform outputs evaluated; dependency builds timed out after 120 seconds |

The full gate was rerun once after fixing an existing documentation link to
a removed blocker file. The first run had 87 checks, 1 failed; all 29
structure rules already passed. Historical reports retain their original
versions and measurements, with current status linked separately.

## Reproduction and comparison

Follow the [README commands](../README.md#build-and-check). Read-only tag
exports supply all six dependencies and their committed flat plugins;
no sibling checkout is modified or built. Core is importable during the
gate, which fails if its eight validators cannot load. The example was
republished through `examples/datacentre/run.py --publish`.

The comparison uses the v0.2.4 committed result as its baseline. All five
archived USDA layers match byte-for-byte after replacing only the axis
producer `0.1.3` with `0.1.2` and the wall producer `0.2.5` with `0.2.4`.
The crate's complete Sdf text matches after replacing only its 19 axis
stamps. Independent USD reads also compare mesh points, face counts,
indices, normals, extents, curve points/counts/widths and world transforms.
Thus the USD result changes only provenance, with no dependency behavior
change affecting this example.

Axis v0.1.3's changelog says “Refresh example pin provenance and
patch-version producer stamps”; v0.1.5 retains that derivation stamp.
The data-centre v0.4.6–v0.4.8 changelog records preservation of published
stages and manifests. These upstream entries agree with the measured
source and geometry comparisons. The wall importer records the package
version in two layer metadata dictionaries.

Fresh 1280 × 800 renders differ slightly from the existing PNGs: mean
absolute RGB channel differences are **0.037692** for the guide view and
**0.037200** for the vanilla view on the 0–255 scale. The original three
PNGs were retained after rendering, and the manifest hashes were refreshed
to describe the retained files. The receipt keeps both old and fresh hashes.
S28 independently rerendered the current crate successfully; its contract
does not require identical pixels across CPU renders.

The single offline attempt used this command with a 120-second limit:

```sh
nix flake check --offline --no-write-lock-file \
  --option substituters '' --option flake-registry '' \
  --override-input toolchain path:../usdaeco-toolchain \
  --override-input core path:../usdaeco-core \
  --override-input axis path:../usdaeco-axis \
  --override-input buildup path:../usdaeco-buildup \
  --override-input ifc path:../usdaeco-ifc \
  --override-input datacentre path:../usdaeco-datacentre \
  --override-input toolchain/core path:./out/pinned/usdaeco-core \
  --override-input toolchain/aeco-toolchain "path:$AECO_BUILD_KIT_ROOT"
```

`AECO_BUILD_KIT_ROOT` names the local build-kit source mirror. The direct
source overrides match the target releases. The test-only nested core
input was overridden with the same v0.9.5 source; the toolchain's own
fixture checks were not run. Public flake URLs retain the nested fixture's
published v0.9.2 tag. No lock file was written, and Nix was not retried.

## Deviations

- Public availability is **not proven** for axis v0.1.5, build-up v0.2.5,
  IFC v0.2.2 and data-centre v0.4.8: anonymous Git probes could not read
  them, and all four public tag pages returned HTTP 404 on 2026-09-12.
  No alternative pins were substituted. The four requested tags must be
  publicly readable before online resolution.
- Nix evaluated current-platform outputs and began dependency builds but
  exceeded the 120-second limit. Completed builds and Linux execution
  remain unproven; local overrides do not prove public resolution.
- Literal byte identity excludes the declared producer metadata in three
  layers and the crate. Fresh-render PNGs were not committed because their
  small pixel differences would add non-provenance changes; retained images
  passed the independent S28 proof.
- Native regeneration, live round trips and numerical clash comparison
  were not run. This release preserves the published tessellation and the
  existing example limitations described in the [use case](usecase.md).
