"""Promote classified wall facts already present in an ordinary USD stage.

Quantity properties are SI, as required by this exchange contract. A reported
width can supply an explicitly labelled equivalent single-layer section; it
cannot recover the original materials, layer order, joins or openings.
"""
from collections import Counter
import math
import os
from pathlib import Path

from pxr import Sdf, Usd
from . import JOIN_NAMES, __version__, register_plugins

WALL_CLASSES = {"IfcWall", "IfcWallStandardCase", "IfcWallElementedCase"}
QUANTITIES = {"Width": "thickness", "GrossSideArea": "grossSideArea",
              "NetSideArea": "netSideArea", "GrossVolume": "grossVolume",
              "NetVolume": "netVolume"}


def classified_walls(stage):
    return [p for p in stage.Traverse() if p.HasAPI("AecoElementAPI") and
            (p.GetAttribute("aeco:class:ifc:code").Get() or "").split(".")[0] in WALL_CLASSES]


def _number(prim, name, *, positive=False):
    value = prim.GetAttribute(name).Get()
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise ValueError("Invalid SI quantity at " + str(prim.GetPath()) + "." + name)
    return float(value)


def export_layers(stage, output, base_path):
    """Split promoted derived properties from drivers before exporting.

    Outputs are new files; the root owns drivers and sublayers the separate
    quantities file above its source. No input or geometry spec is rewritten.
    """
    output, base_path = Path(output).resolve(), Path(base_path).resolve()
    quantities = output.with_name(output.stem + ".derived.usda")
    if output.exists() or quantities.exists() or output == base_path:
        raise ValueError("Output and derived companion must be new paths")
    driver = Sdf.Layer.CreateAnonymous("wall.drivers.usda")
    driver.TransferContent(stage.GetRootLayer())
    derived = Sdf.Layer.CreateAnonymous("wall.derived.usda")
    derived.customLayerData = {"aeco:wall:layer": "derived", "aeco:wall:producer": "aeco-wall " + __version__}
    # Traverse authored specs, including catalog classes, and resolve the flag
    # through the schema registry (stage data never authors aecoDerived).
    paths = []
    driver.Traverse(Sdf.Path.absoluteRootPath, lambda path: paths.append(path) if path.IsPropertyPath() else None)
    for path in paths:
        prop = stage.GetPropertyAtPath(path)
        if prop and prop.GetMetadata("aecoDerived") is True:
            Sdf.CreatePrimInLayer(derived, path.GetPrimPath())
            Sdf.CopySpec(driver, path, derived, path)
            driver.GetPrimAtPath(path.GetPrimPath()).RemoveProperty(driver.GetPropertyAtPath(path))
    driver.subLayerPaths = [quantities.name, os.path.relpath(base_path, output.parent)]
    output.parent.mkdir(parents=True, exist_ok=True)
    if not derived.Export(str(quantities)) or not driver.Export(str(output)):
        raise RuntimeError("Could not export wall layers")
    return quantities


def import_stage(source, output):
    """Write an additive wall overlay; never infer topology from mesh proximity."""
    register_plugins()
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists() or output.with_name(output.stem + ".derived.usda").exists() or source == output:
        raise ValueError("Output and derived companion must be new paths")
    base = Usd.Stage.Open(str(source))
    if not base or base.GetCompositionErrors():
        raise ValueError("Source stage must compose")
    layer = Sdf.Layer.CreateAnonymous("wall.drivers.usda")
    layer.subLayerPaths = [str(source)]
    layer.customLayerData = {"aeco:wall:layer": "drivers", "aeco:wall:producer": "aeco-wall " + __version__,
                            "aeco:wall:sectionEvidence": "equivalent single layer from reported SI width; materials and priorities unknown"}
    stage = Usd.Stage.Open(layer)
    for key in ("defaultPrim", "metersPerUnit", "upAxis", "fallbackPrimTypes"):
        if base.HasAuthoredMetadata(key):
            stage.SetMetadata(key, base.GetMetadata(key))
    stats = Counter(dict.fromkeys(("AecoWallAPI", "AecoBuildUpAPI", "AecoOpeningAPI", "axesReused", "missingAxes",
                                  "joinTargets", "propsBlocked", "equivalentSections", "missingWidths", "missingHeights"), 0))
    widths_by_type = {}
    walls = classified_walls(stage)
    ids = [p.GetAttribute("aeco:id").Get() for p in walls]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("Wall identities must be present and unique")
    for wall in walls:
        wall.ApplyAPI("AecoWallAPI")
        stats["AecoWallAPI"] += 1
        stats["axesReused" if wall.HasAPI("AecoAxisAPI") else "missingAxes"] += 1
        # Published quantities do not describe material usage. Avoid presenting
        # a fallback location line as source evidence.
        for name in ("locationLine", "flipped"):
            if not wall.GetAttribute("aeco:wall:" + name).HasAuthoredValueOpinion():
                wall.GetAttribute("aeco:wall:" + name).Block()
        for source_name, target in (("IsExternal", "isExternal"), ("LoadBearing", "loadBearing")):
            raw = wall.GetAttribute("aeco:props:Pset_WallCommon:" + source_name)
            value = raw.Get()
            if value is not None:
                if not isinstance(value, bool):
                    raise ValueError("Wall semantic flag must be boolean: " + source_name)
                wall.GetAttribute("aeco:wall:" + target).Set(value)
                raw.Block(); stats["propsBlocked"] += 1
        prefix = "aeco:props:Qto_WallBaseQuantities:"
        height = _number(wall, prefix + "Height", positive=True)
        if height is None:
            wall.GetAttribute("aeco:wall:height").Block(); stats["missingHeights"] += 1
        else:
            wall.GetAttribute("aeco:wall:height").Set(height)
            wall.GetAttribute(prefix + "Height").Block(); stats["propsBlocked"] += 1
        width = _number(wall, prefix + "Width", positive=True)
        if width is None:
            stats["missingWidths"] += 1
        else:
            catalogs = [stage.GetPrimAtPath(p) for p in wall.GetInherits().GetAllDirectInherits()]
            catalogs = [p for p in catalogs if p and p.IsAbstract() and p.HasAPI("AecoTypeAPI")]
            if len(catalogs) != 1:
                raise ValueError("Reported width requires exactly one inherited catalog type")
            catalog = catalogs[0]
            previous = widths_by_type.setdefault(catalog.GetPath(), width)
            if abs(previous - width) > 1e-8:
                raise ValueError("Conflicting widths on a shared wall type")
            if not catalog.HasAPI("AecoBuildUpAPI"):
                catalog.ApplyAPI("AecoBuildUpAPI")
                for name, value in {"thicknesses": [width], "functions": ["other"], "materials": [""], "priorities": [0]}.items():
                    catalog.GetAttribute("aeco:buildUp:" + name).Set(value)
                catalog.GetAttribute("aeco:buildUp:totalThickness").Set(width)
                catalog.SetCustomDataByKey("aeco:wall:sectionEvidence", "equivalent single layer from reported width")
                stats["AecoBuildUpAPI"] += 1; stats["equivalentSections"] += 1
        for raw_name, target in QUANTITIES.items():
            value = _number(wall, prefix + raw_name, positive=raw_name == "Width")
            if value is not None:
                wall.GetAttribute("aeco:wall:" + target).Set(value)
                wall.GetAttribute(prefix + raw_name).Block(); stats["propsBlocked"] += 1
        stats["joinTargets"] += sum(len(wall.GetRelationship("aeco:wall:" + n).GetTargets()) for n in JOIN_NAMES)
    stats["AecoOpeningAPI"] = sum(p.HasAPI("AecoOpeningAPI") for p in stage.Traverse())
    export_layers(stage, output, source)
    return dict(stats)
