# Portable example verification

Version 0.2.3 uses toolchain 0.3.6. Sources and consumer checkouts were placed in
two different directory layouts; the second started without inputs/source or
transient out/ files. Each full gate ran the pinned example and created its own
runtime source link. Dependency releases were exported from tags without
modifying their source checkouts.

| Acceptance | Working layout | Relocated layout |
|---|---|---|
| Full check.py | 87 checks, 0 failed | 87 checks, 0 failed |
| Structure including S29 | 29/29 PASS | 29/29 PASS |
| Fresh result / ResultStale | PASS | PASS |
| S27 plugin-free crate | PASS | PASS |
| S28 independent stock render | PASS | PASS |
| Core UsdValidation rules loaded | 8/8 | 8/8 |

[Machine-readable gate results](relocation-verification.json) retain every check
in both layouts. The archived wall driver layer also opens independently
with no family plugins and zero composition errors after relocation.

Source pytest: **24 passed**. Exact integration pins are recorded in
[dependencies.json](../dependencies.json): core v0.9.2, axis v0.1.2,
IFC v0.2.0, data centre v0.4.5 and the proposed toolchain v0.3.6 source.
Wall additionally uses build-up v0.2.1.

The committed crate and all PNGs are byte-identical to v0.2.2. Regeneration
proved the same canonical crate content; existing valid images were retained
because independent Embree renders need not have identical pixels. The source
layer hashes, findings, geometry and schema property contract are unchanged.
Wall changes one source-reference line and two producer-version lines
(0.2.2 to 0.2.3) in its review layers; the manifest records the new hashes and pin.

The result totals **2,549,113 bytes**. The runtime `inputs/source` link is ignored
and is absent from the committed file inventory.

## Reproduction

Use the source environment in [README](../README.md#build-and-check), selecting
the exact dependency releases above. Run the gate with an importable core:

```sh
export PYTHONDONTWRITEBYTECODE=1
env -u PYTHONPATH PYTHONPATH="$AECO_CORE_ROOT:$PWD" "$PYTHON" check.py
env -u PYTHONPATH PYTHONPATH="$AECO_CORE_ROOT:$PWD" "$PYTHON" -m pytest -q
```

Export this commit into a second directory with `git archive`, and independently
copy the pinned data-centre release beneath a different dependency directory.
Set `AECO_DATACENTRE_ROOT` to that copy and update the core/axis/IFC (and, for
walls, build-up) root and plugin variables for their copied releases. Run the
same command from the second consumer root. `run.py` recreates `inputs/source`;
no matching sibling name, out/pinned directory or pre-existing symlink is needed.
S29 verifies source paths relative to the archived layer, so
`result/layers/out/` uses `../../../inputs/source/dist/clash/dc.usda`.

## Other examples surveyed

The read-only survey covered 19 committed result trees in 14 repositories.
Only wall v0.2.2 and pipe v0.2.2 carried this checkout-location defect.
CCTV v0.5.3 has a separate missing archived `source-data/dc.usda` reference;
Bonsai v0.1.3 references `dc.geometry.usdc` where the archive contains
`dc.geometry.usda`. Both also fail S29 and are left for their own releases.
The other 15 trees pass: six core v0.9.3 examples, axis v0.1.3, build-up v0.2.2,
IFC v0.2.1, Revit v0.1.3, clash v0.2.1, solid v0.1.2, plan v0.1.1,
compliance v0.1.1 and typical v0.1.1. The survey is a source-path check,
not a rerun of those repositories' complete gates.

## Deviations

- Adding S29 to S01–S28 produces 29 rules, so the requested “28/0 including S29”
  is reported as 29/0.
- Wall also refreshes two producer-version metadata lines for the patch release;
  claiming that only reference lines changed would omit those provenance changes.
- One `nix flake check --offline --no-write-lock-file` attempt failed at public
  axis v0.1.2 input resolution with HTTP 404; builds and native execution are
  not proven, and no second attempt was made.
- The toolchain v0.3.6 source was tested before its release tag exists. Merge and
  tag that toolchain release before resolving the new consumer flake pins.
