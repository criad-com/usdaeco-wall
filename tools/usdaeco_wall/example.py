"""Route K on the published clash variant; all source data stays read-only."""
import hashlib
import json
import math
import os
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom
from . import ROOT, iter_walls
from .stage_import import import_stage


def published_source():
    root = Path(os.environ.get("AECO_DATACENTRE_ROOT", ROOT.parent / "usdaeco-datacentre"))
    source = Path(os.environ.get("AECO_DATACENTRE_STAGE", root / "dist/clash/dc.usda")).resolve()
    manifest_path = source.with_name("dc.manifest.json")
    manifest = json.loads(manifest_path.read_text())
    if manifest["variant"] != "clash" or manifest["facility"] != "demo-datacentre-01":
        raise ValueError("Example requires the published clash variant")
    for name, info in manifest["layers"].items():
        path = source.parent / name
        if path.stat().st_size != info["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
            raise ValueError("Published layer differs from dc.manifest.json: " + name)
    return source, manifest


def source_counts(stage):
    elements = [p for p in stage.Traverse() if p.HasAPI("AecoElementAPI")]
    return {"elements": len(elements), "levels": sum(p.GetTypeName() == "AecoLevel" for p in stage.Traverse()),
            "spaces": sum(p.GetTypeName() == "AecoSpace" for p in stage.Traverse()),
            "ports": sum(p.GetTypeName() == "AecoPort" for p in stage.Traverse()),
            "meshes": sum(p.IsA(UsdGeom.Mesh) for p in stage.Traverse()),
            "unclassified": sum((p.GetAttribute("aeco:class:ifc:code").Get() or "").split(".")[0] in ("", "IfcBuildingElementProxy") for p in elements),
            "unparented": sum(not any(a.GetTypeName() in {"AecoSite", "AecoFacility", "AecoFacilityPart", "AecoLevel", "AecoSpace"}
                                      for a in ancestors(p)) for p in elements)}


def ancestors(prim):
    parent = prim.GetParent()
    while parent and not parent.IsPseudoRoot():
        yield parent
        parent = parent.GetParent()


def office_walls(stage):
    return [p for p in iter_walls(stage) if any(a.GetName() == "L01_Office" for a in ancestors(p))]


def frame_corner(stage, target):
    """Display the planted partition corner, framed from its composed bounds."""
    selected_names = {"wall_l1_h_007", "wall_l1_v_016", "pipe_clash_hard"}
    selected = [p for p in stage.Traverse() if p.GetName() in selected_names]
    if {p.GetName() for p in selected} != selected_names:
        raise ValueError("Published stage is missing the corridor/meeting-room corner")
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "proxy", "render"])
    bounds = Gf.Range3d()
    for prim in selected:
        bounds.UnionWith(cache.ComputeWorldBound(prim).ComputeAlignedRange())
    if bounds.IsEmpty():
        raise ValueError("Corner has no renderable bounds")
    layer = Sdf.Layer.CreateNew(str(target))
    stage.GetRootLayer().subLayerPaths.insert(0, str(target))
    keep = [p.GetPath() for p in selected]
    hidden_extents = 0
    with Usd.EditContext(stage, layer):
        for prim in stage.Traverse():
            if not prim.IsA(UsdGeom.Gprim):
                continue
            extent = prim.GetAttribute("aeco:derived:role").Get() == "extent"
            hidden_extents += int(extent)
            if extent or not any(prim.GetPath().HasPrefix(path) for path in keep):
                UsdGeom.Imageable(prim).CreateVisibilityAttr("invisible")
            else:
                color = (0.95, 0.23, 0.06) if any(a.GetName() == "pipe_clash_hard" for a in ancestors(prim)) else (0.56, 0.69, 0.77)
                UsdGeom.Gprim(prim).CreateDisplayColorAttr([color])
                # The source uses material bindings; the review overlay uses
                # displayColor so the single crossing pipe remains legible.
                prim.CreateRelationship("material:binding").SetTargets([])
        camera = UsdGeom.Camera(stage.GetPrimAtPath("/Renders/partition_corner"))
        if not camera:
            raise ValueError("inputs/cameras.usda must define partition_corner")
        center, radius = bounds.GetMidpoint(), bounds.GetSize().GetLength() / 2
        distance = radius / math.sin(math.atan(15 / (2 * 45))) * 1.12
        eye = center + Gf.Vec3d(-1, -1.6, 1.1).GetNormalized() * distance
        camera.MakeMatrixXform().Set(Gf.Matrix4d().SetLookAt(eye, center, Gf.Vec3d(0, 0, 1)).GetInverse())
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.1, distance * 4))
    layer.customLayerData = {"aeco:wall:layer": "review", "aeco:wall:framing": "composed corner bounds; extents excluded"}
    layer.Save()
    return hidden_extents


def hook(stage, out_dir):
    source, manifest = published_source()
    base = Usd.Stage.Open(str(source))
    actual = source_counts(base)
    if actual != manifest["counts"]:
        raise ValueError("Published stage census differs from dc.manifest.json")
    root = stage.GetRootLayer()
    root.Save()
    # The same implementation backs `aeco-wall import`; this call never opens IFC.
    drivers = out_dir / "wall.drivers.usda"
    stats = import_stage(source, drivers)
    # Both layers live in out/: reuse the harness's portable source spelling.
    driver_layer = Sdf.Layer.FindOrOpen(str(drivers))
    driver_layer.subLayerPaths = [driver_layer.subLayerPaths[0], root.subLayerPaths[-1]]
    driver_layer.Save()
    root.subLayerPaths.insert(0, str(drivers))
    root.Save()
    walls = office_walls(stage)
    # Restrict the axis companion to the 19 office-wing wall paths measured in
    # this source. The count itself is derived, never a selection constant.
    masked = Usd.Stage.OpenMasked(root, Usd.StagePopulationMask([p.GetPath() for p in walls]))
    from usdaeco_axis.derive import derive
    axes = derive(masked, out_dir / "axis.derived.usda")
    root.subLayerPaths.insert(0, str(out_dir / "axis.derived.usda"))
    from .validators import validate_stage
    from usdaeco_check.validation import run
    wall_errors = validate_stage(stage, include_builtin=False)
    axis_errors = run(Usd.Stage.OpenMasked(root, Usd.StagePopulationMask([p.GetPath() for p in walls])), ["UsdAecoAxisValidators"])
    findings = [{"name": e.GetName(), "severity": str(e.GetType()).split(".")[-1].lower(),
                 "paths": [str(site.GetPath()) for site in e.GetSites()], "message": e.GetMessage()} for e in wall_errors + axis_errors]
    hidden = frame_corner(stage, out_dir / "review.usda")
    return [{"name": "PublishedCounts", "counts": actual},
            {"name": "WallPromotion", "counts": stats},
            {"name": "OfficeWallAxes", "count": axes["axes"]},
            {"name": "ValidatorFindings", "count": len(findings), "findings": findings},
            {"name": "ReviewExtentGuidesExcluded", "count": hidden}]
