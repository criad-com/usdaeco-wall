# Wall drivers and opening relationships

`AecoWallAPI` decorates an existing wall occurrence. Its section is an
inherited catalog build-up, its path uses the shared axis API, and its
body is derived by the authoring kernel. `AecoOpeningAPI` remains in this
library as the five-property seed of a future opening module.

Read the [minimal example](../examples/minimal.usda) for a three-wall L/T
join, a hosted opening, an inherited three-layer catalog and guide axes.
The [Route K walkthrough](../../docs/usecase.md) applies promotion and
axis derivation to a pinned published facility. Its image below shows
the real tessellated partition corner; the minimal fixture carries guide
geometry only.

![Published partition corner](usdAecoWallExample.png)

Register the codeless schema and dependencies before querying APIs. The
`usdAecoWallValidators` Python plugin exposes six rules under the keyword
`UsdAecoWallValidators`. The stage's applied schema identifiers remain
`AecoWallAPI` and `AecoOpeningAPI`; generated Tf type names are
`UsdAecoWallWallAPI` and `UsdAecoWallOpeningAPI`.

Drivers and derived values have different owners. Editable height is
unconnected unless a top-level constraint is supplied. Reported thickness,
areas and volumes carry `aecoDerived` in the schema and are written in
separate derived layers. Nothing in this schema introduces a gprim or
changes the core spatial structure.
