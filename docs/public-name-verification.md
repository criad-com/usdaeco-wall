# Public repository name verification

Version **0.2.4** changes six flake inputs and two README links to the public
`criad-com` organization. Toolchain is pinned to **v0.3.8**; the core, axis,
build-up, IFC and data-centre refs and historical fixtures remain unchanged.

| Acceptance | Measured result |
|---|---|
| Full source gate | 87 checks, 0 failed, 0 not run |
| Behavioral checks | 58 checks, 0 failed |
| Structure under toolchain v0.3.8 | S01–S29: 29 checks, 0 failed |
| Public inputs and sanitization | S05 and S25 PASS |
| Previous public organization references | 0 remaining in repository sources |
| Source-run pytest | 24 passed |
| Schema compiler validation | PASS; both schema files unchanged |
| UsdValidation plugins | 6 wall and 8 core validators loaded; seeded identity defect detected |
| Fresh example comparison | PASS; 12,375 plugin-free prims, 1 non-blank review render |
| Published wall coverage | 92 walls, 19 L01 axes, 3 equivalent single-layer types |
| Published meshes | 3,015; topology and transforms preserved |
| S27 / S28 / S29 | PASS: relocated crate, independent stock render and portable source paths |
| Retained result | 8 files, 2,549,113 bytes; crate and all PNGs byte-identical to v0.2.3 |
| Nix | 1 attempt; corrected public axis v0.1.2 URL returned HTTP 404 before building |

Checks ran from source without an installed wall package or setuptools.
Read-only tag exports supplied core v0.9.2, axis v0.1.2, build-up v0.2.1,
IFC v0.2.0 and data centre v0.4.5. The tested toolchain source has Git tree
`bc9ec25798a9dc681f01e83e5ba3e6c1cf1fedbf`, identical to released v0.3.8;
the release tag was verified before submitting this change. No dependency
checkout was modified or built.

Use the pinned environment described in the [README](../README.md#build-and-check):

```sh
export PYTHONDONTWRITEBYTECODE=1
bash build.sh --generate-only
bash build.sh --install-root out
env -u PYTHONPATH PYTHONPATH="$AECO_CORE_ROOT:$PWD" "$PYTHON" check.py --report out/check.json
env -u PYTHONPATH "$PYTHON" -m pytest -q
```

## Deviations

- The example manifest must record the new toolchain pin for S22. Bumping
  the wall version also changes the producer stamp in each of the two archived
  wall layers, which the fresh-result comparison checks byte-for-byte. Those
  two metadata lines and their manifest hashes were refreshed to keep the gate
  green. The committed crate, images, findings, source hashes and geometry were
  retained; the example was not republished with `--publish`.
- The single `nix flake check --no-write-lock-file` attempt reached
  `github:criad-com/usdaeco-axis?ref=v0.1.2` but its public source returned
  HTTP 404. Input availability, Nix builds and cross-platform execution remain
  unproven; no retry or dependency-pin substitution was made.
- Native regeneration, live round trips and numerical clash comparison were
  not run: this patch changes public names and release metadata. Existing
  example limitations remain as documented in the [use case](usecase.md).
