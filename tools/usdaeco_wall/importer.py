"""Promote wall, layered section, join and opening facts above a core stage."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import uuid

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.guid
import ifcopenshell.util.element as element
import ifcopenshell.util.placement as placement
import ifcopenshell.util.shape as shape
import ifcopenshell.util.unit as unit
import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom

from . import APIS, SIZE_TOLERANCE, __version__, register_plugins, section_offsets

JOIN_TYPES = {"ATSTART": "joinAtStart", "ATEND": "joinAtEnd", "ATPATH": "joinAlongPath"}
FUNCTIONS = {"structure": "structure", "structural": "structure", "substrate": "substrate",
             "insulation": "insulation", "finish": "finish", "finish1": "finish",
             "finish2": "finish", "membrane": "membrane", "other": "other"}


def _uid(entity):
    return str(uuid.UUID(hex=ifcopenshell.guid.expand(entity.GlobalId)))


def _set(prim, name, value):
    if value is not None:
        prim.GetAttribute(name).Set(value)


def _catalog(prim):
    for path in prim.GetInherits().GetAllDirectInherits():
        candidate = prim.GetStage().GetPrimAtPath(path)
        if candidate and candidate.IsAbstract() and candidate.HasAPI("AecoTypeAPI"):
            return candidate
    return None


def _block(prim, pset, field, stats):
    attr = prim.GetAttribute("aeco:props:" + pset + ":" + field)
    if attr and attr.HasValue():
        attr.Block()
        stats["propsBlocked"] += 1


def _quantity(model, entity, name, dimension):
    data = element.get_pset(entity, "Qto_WallBaseQuantities", name, verbose=True)
    if not data or data.get("value") is None:
        return None
    quantity = model.by_id(data["id"])
    source = quantity.Unit or unit.get_project_unit(model, "AREAUNIT" if dimension == 2 else "VOLUMEUNIT")
    if source:
        # IFC area/volume SI prefixes are powers of the length prefix.
        factor = unit.convert_unit(1.0, source, model.create_entity(
            "IfcSIUnit", UnitType="AREAUNIT" if dimension == 2 else "VOLUMEUNIT",
            Name="SQUARE_METRE" if dimension == 2 else "CUBIC_METRE"))
    else:
        factor = unit.calculate_unit_scale(model) ** dimension
    return float(data["value"]) * factor


def _opening_geometry(entity, scale, metres):
    """Local bounding dimensions from the IFC cut, in SI, plus its placement.

    No meshes are authored. Tessellation is only used to measure the opening
    envelope; nonrectangular cuts retain their IFC source representation.
    """
    geometry = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), entity)
    vertices = np.array(geometry.geometry.verts).reshape(-1, 3)  # geometry engine outputs SI
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    local_origin = np.array([(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2]])
    matrix = placement.get_local_placement(entity.ObjectPlacement).copy()
    matrix[:3, 3] *= scale
    matrix[:3, 3] += matrix[:3, :3] @ local_origin
    matrix[:3, 3] /= metres
    return float(high[0] - low[0]), float(high[2] - low[2]), Gf.Matrix4d(*matrix.T.flatten().tolist())


def import_wall(core_stage, ifc_file, output="kind.usda"):
    """Write a new additive kind layer and return explicit import counts.

    Both inputs stay unchanged. Unsupported usage offsets are blocked and
    counted, not coerced to a different location line. Axes are never authored.
    """
    register_plugins()
    core_stage, ifc_file, output = (Path(p).resolve() for p in (core_stage, ifc_file, output))
    if output in (core_stage, ifc_file) or output.exists() or output.with_name(output.stem + ".derived.usda").exists():
        raise ValueError("Output must be a new file distinct from both inputs")
    model = ifcopenshell.open(str(ifc_file))
    base = Usd.Stage.Open(str(core_stage))
    if not base or base.GetCompositionErrors():
        raise ValueError("Core stage must compose successfully")
    scale = unit.calculate_unit_scale(model)
    layer = Sdf.Layer.CreateAnonymous("kind.usda")
    layer.subLayerPaths = [str(core_stage)]
    stage = Usd.Stage.Open(layer)
    for key in ("defaultPrim", "upAxis", "metersPerUnit", "fallbackPrimTypes"):
        if base.HasAuthoredMetadata(key):
            stage.SetMetadata(key, base.GetMetadata(key))
    layer.customLayerData = {"aeco:wall:layer": "drivers", "aeco:wall:producer": "aeco-wall " + __version__}
    metres = UsdGeom.GetStageMetersPerUnit(stage)
    index = {}
    for prim in stage.Traverse():
        identity = prim.GetAttribute("aeco:id").Get()
        if identity:
            if identity in index:
                raise ValueError("Core stage has duplicate aeco:id: " + identity)
            index[identity] = prim
    stats = Counter({name: 0 for name in (*APIS, "AecoBuildUpAPI", "axesReused", "missingAxes",
        "joinTargets", "unsupportedJoins", "unsupportedLocationLines", "propsBlocked", "unmatched",
        "fillings", "openingDimensionsUnavailable", "catalogsCreated", "layerFunctionsOther")})
    applied = set()

    def apply(prim, api):
        key = (prim.GetPath(), api)
        if key not in applied:
            if not prim.CanApplyAPI(api):
                raise ValueError("Cannot apply " + api + " to " + str(prim.GetPath()))
            prim.ApplyAPI(api)
            applied.add(key)
            stats[api] += 1

    rows_by_type = {}
    walls = {}
    for entity in model.by_type("IfcWall"):
        prim = index.get(_uid(entity))
        if prim is None:
            stats["unmatched"] += 1
            continue
        walls[entity.id()] = prim
        apply(prim, "AecoWallAPI")
        stats["axesReused" if prim.HasAPI("AecoAxisAPI") else "missingAxes"] += 1
        material = element.get_material(entity, should_skip_usage=True)
        usage = element.get_material(entity)
        widths, functions = [], []
        if material and material.is_a("IfcMaterialLayerSet"):
            layers = material.MaterialLayers
            widths = [float(l.LayerThickness) * scale for l in layers]
            functions = [FUNCTIONS.get("".join((getattr(l, "Category", "") or "").lower().split()), "other") for l in layers]
            stats["layerFunctionsOther"] += functions.count("other")
            materials = [l.Material.Name or "" if l.Material else "" for l in layers]
            priorities = [int(getattr(l, "Priority", 0) or 0) for l in layers]
            catalog = _catalog(prim)
            if catalog is None:
                root = stage.GetDefaultPrim().GetPath() if stage.GetDefaultPrim() else Sdf.Path.absoluteRootPath
                catalog_path = root.AppendChild("_TypeCatalog").AppendChild("BuildUp_" + str(material.id()))
                if not stage.GetPrimAtPath(catalog_path):
                    stage.CreateClassPrim(catalog_path.GetParentPath())
                    catalog = stage.CreateClassPrim(catalog_path)
                    catalog.ApplyAPI("AecoTypeAPI")
                    stats["catalogsCreated"] += 1
                else:
                    catalog = stage.GetPrimAtPath(catalog_path)
                prim.GetInherits().AddInherit(catalog_path)
            rows = (widths, functions, materials, priorities)
            if catalog.GetPath() in rows_by_type and rows_by_type[catalog.GetPath()] != rows:
                raise ValueError("Conflicting material layer sets on a shared catalog type")
            rows_by_type[catalog.GetPath()] = rows
            apply(catalog, "AecoBuildUpAPI")
            for name, values in zip(("thicknesses", "functions", "materials", "priorities"), rows):
                _set(catalog, "aeco:buildUp:" + name, values)
            _set(catalog, "aeco:buildUp:totalThickness", sum(widths))
            _set(prim, "aeco:wall:thickness", sum(widths))
        if usage and usage.is_a("IfcMaterialLayerSetUsage"):
            flipped = usage.DirectionSense == "NEGATIVE"
            _set(prim, "aeco:wall:flipped", flipped)
            sign = -1 if flipped else 1
            offset = float(usage.OffsetFromReferenceLine) * scale
            options = section_offsets(widths, functions)
            token = next((name for name, reference in options.items()
                          if abs(offset + sign * reference) <= SIZE_TOLERANCE), None)
            if not widths or usage.LayerSetDirection != "AXIS2":
                token = None
            if token:
                _set(prim, "aeco:wall:locationLine", token)
            else:
                prim.GetAttribute("aeco:wall:locationLine").Block()
                stats["unsupportedLocationLines"] += 1
        else:
            prim.GetAttribute("aeco:wall:locationLine").Block()
            stats["unsupportedLocationLines"] += 1
        extrusions = shape.get_base_extrusions(entity) or []
        if extrusions:
            _set(prim, "aeco:wall:height", float(extrusions[0].Depth) * scale)
        else:
            prim.GetAttribute("aeco:wall:height").Block()
        container = element.get_container(entity)
        level = index.get(_uid(container)) if container else None
        if level and level.IsA("AecoLevel"):
            prim.GetRelationship("aeco:wall:baseLevel").SetTargets([level.GetPath()])
            cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            wp = cache.GetLocalToWorldTransform(prim).ExtractTranslation()
            lp = cache.GetLocalToWorldTransform(level).ExtractTranslation()
            up = 2 if UsdGeom.GetStageUpAxis(stage) == "Z" else 1
            _set(prim, "aeco:wall:baseOffset", float(wp[up] - lp[up]) * metres)
        for source, target in (("IsExternal", "isExternal"), ("LoadBearing", "loadBearing")):
            value = element.get_pset(entity, "Pset_WallCommon", source)
            if isinstance(value, bool):
                _set(prim, "aeco:wall:" + target, value)
                _block(prim, "Pset_WallCommon", source, stats)
                catalog = _catalog(prim)
                if catalog:
                    _block(catalog, "Pset_WallCommon", source, stats)
        for source, target, dimension in (("GrossSideArea", "grossSideArea", 2),
            ("NetSideArea", "netSideArea", 2), ("GrossVolume", "grossVolume", 3), ("NetVolume", "netVolume", 3)):
            value = _quantity(model, entity, source, dimension)
            if value is not None:
                _set(prim, "aeco:wall:" + target, value)
                _block(prim, "Qto_WallBaseQuantities", source, stats)
    for rel in model.by_type("IfcRelConnectsPathElements"):
        a, b = walls.get(rel.RelatingElement.id()), walls.get(rel.RelatedElement.id())
        if a is None or b is None:
            continue
        # Preserve every representable direction. NOTDEFINED/NOTATPATH have
        # no equivalent driver and are counted rather than invented as ATPATH.
        for prim, peer, end in ((a, b, rel.RelatingConnectionType), (b, a, rel.RelatedConnectionType)):
            if end in JOIN_TYPES:
                prim.GetRelationship("aeco:wall:" + JOIN_TYPES[end]).AddTarget(peer.GetPath())
                stats["joinTargets"] += 1
            else:
                stats["unsupportedJoins"] += 1
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    for rel in model.by_type("IfcRelVoidsElement"):
        host = walls.get(rel.RelatingBuildingElement.id())
        if host is None:
            continue
        entity = rel.RelatedOpeningElement
        opening = index.get(_uid(entity))
        created = opening is None
        if created:
            opening = stage.DefinePrim(host.GetPath().AppendChild("Opening_" + _uid(entity).replace("-", "")), "Xform")
            opening.ApplyAPI("AecoElementAPI")
            _set(opening, "aeco:id", _uid(entity))
            opening.ApplyAPI("AecoClassificationAPI", "ifc")
            _set(opening, "aeco:class:ifc:code", entity.is_a())
        apply(opening, "AecoOpeningAPI")
        opening.GetRelationship("aeco:opening:host").SetTargets([host.GetPath()])
        try:
            width, height, world = _opening_geometry(entity, scale, metres)
        except (RuntimeError, ValueError):
            stats["openingDimensionsUnavailable"] += 1
            for name in ("width", "height", "sillHeight"):
                opening.GetAttribute("aeco:opening:" + name).Block()
            if created:
                # Keep a valid placement even when dimensions are unavailable.
                matrix = placement.get_local_placement(entity.ObjectPlacement).copy()
                matrix[:3, 3] *= scale / metres
                world = Gf.Matrix4d(*matrix.T.flatten().tolist())
        else:
            _set(opening, "aeco:opening:width", width)
            _set(opening, "aeco:opening:height", height)
            up = 2 if UsdGeom.GetStageUpAxis(stage) == "Z" else 1
            sill = (world.ExtractTranslation()[up] - cache.GetLocalToWorldTransform(host).ExtractTranslation()[up]) * metres
            _set(opening, "aeco:opening:sillHeight", float(sill))
        if created:
            parent_world = cache.GetLocalToWorldTransform(opening.GetParent())
            UsdGeom.Xformable(opening).MakeMatrixXform().Set(world * parent_world.GetInverse())
        for filling_rel in entity.HasFillings:
            filling = index.get(_uid(filling_rel.RelatedBuildingElement))
            if filling is not None:
                opening.GetRelationship("aeco:opening:filling").AddTarget(filling.GetPath())
                stats["fillings"] += 1
            else:
                stats["unmatched"] += 1
    from .stage_import import export_layers
    export_layers(stage, output, core_stage)
    return dict(stats)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="aeco-wall-import", description=__doc__)
    parser.add_argument("core_stage")
    parser.add_argument("ifc")
    parser.add_argument("-o", "--out", default="kind.usda")
    args = parser.parse_args(argv)
    try:
        stats = import_wall(args.core_stage, args.ifc, args.out)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, "aeco-wall-import: " + str(exc) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
