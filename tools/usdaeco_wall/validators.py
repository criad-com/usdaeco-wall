"""Six default-time wall validators; geometry checks cover straight axes."""
import math
from .profiles import apply_profile, load_profile
from pxr import Gf, Usd, UsdGeom, UsdValidation
from . import (GEOMETRY_TOLERANCE, JOIN_NAMES, SIZE_TOLERANCE, iter_walls,
               section_offsets)

KEYWORD = "UsdAecoWallValidators"


def _issue(name, prims, message, error=False):
    severity = UsdValidation.ValidationErrorType.Error if error else UsdValidation.ValidationErrorType.Warn
    return UsdValidation.ValidationError(name, severity, [
        UsdValidation.ValidationErrorSite(p.GetStage(), p.GetPath()) for p in prims], message)


def _kind(prim, time_range):
    if prim.HasAPI("AecoWallAPI"):
        code = prim.GetAttribute("aeco:class:ifc:code").Get() or ""
        if code.split(".")[0] not in ("IfcWall", "IfcWallStandardCase", "IfcWallElementedCase"):
            return [_issue("WallKindMismatch", [prim], "Wall API has incompatible IFC classification: " + code)]
    return []


def _axis(prim, time_range):
    if prim.HasAPI("AecoWallAPI") and (not prim.HasAPI("AecoAxisAPI") or any(
        prim.GetAttribute("aeco:axis:" + n).Get() is None for n in ("start", "end"))):
        return [_issue("WallMissingAxis", [prim], "Wall requires a readable AecoAxisAPI", True)]
    return []


def _joins(prim, time_range):
    issues = []
    if not prim.HasAPI("AecoWallAPI"):
        return issues
    for name in JOIN_NAMES:
        for target in prim.GetRelationship("aeco:wall:" + name).GetTargets():
            peer = prim.GetStage().GetPrimAtPath(target)
            if not peer or not peer.HasAPI("AecoWallAPI") or not any(
                prim.GetPath() in peer.GetRelationship("aeco:wall:" + n).GetTargets() for n in JOIN_NAMES):
                issues.append(_issue("WallJoinAsymmetric", [prim], "Join has no reciprocal wall target: " + str(target)))
    return issues


def _line(prim):
    if not prim.HasAPI("AecoAxisAPI") or prim.GetAttribute("aeco:axis:curve").Get() != "line":
        return None
    a, b = (prim.GetAttribute("aeco:axis:" + n).Get() for n in ("start", "end"))
    if a is None or b is None or (b - a).GetLength() < 1e-12:
        return None
    return a, b


def _segment_distance(point, a, b):
    delta = b - a
    denom = Gf.Dot(delta, delta)
    t = max(0.0, min(1.0, Gf.Dot(point - a, delta) / denom)) if denom else 0.0
    return (point - (a + t * delta)).GetLength()


def _footprint(prim, cache, metres):
    line = _line(prim)
    thickness = prim.GetAttribute("aeco:wall:thickness").Get()
    if not line or not thickness or thickness <= 0:
        return None
    a, b = line
    up = Gf.Vec3d(0, 0, 1) if UsdGeom.GetStageUpAxis(prim.GetStage()) == "Z" else Gf.Vec3d(0, 1, 0)
    normal = Gf.Cross(up, b - a)
    if normal.GetLength() < 1e-12:
        return None
    normal.Normalize()
    widths = list(prim.GetAttribute("aeco:buildUp:thicknesses").Get() or [thickness])
    functions = list(prim.GetAttribute("aeco:buildUp:functions").Get() or [])
    reference = section_offsets(widths, functions).get(prim.GetAttribute("aeco:wall:locationLine").Get())
    if reference is None:
        return None
    sign = -1 if prim.GetAttribute("aeco:wall:flipped").Get() else 1
    offsets = (-sign * reference / metres, sign * (thickness - reference) / metres)
    matrix = cache.GetLocalToWorldTransform(prim)
    return [matrix.Transform(p + normal * offset) for p, offset in
            ((a, offsets[0]), (b, offsets[0]), (b, offsets[1]), (a, offsets[1]))]


def _extended(stage, time_range):
    issues = []
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    metres = UsdGeom.GetStageMetersPerUnit(stage)
    up = 2 if UsdGeom.GetStageUpAxis(stage) == "Z" else 1
    # Plan-face distance: elevation constraints belong to the adapter. Retain
    # finite face spans, including end caps, so distant collinear walls fail.
    def plan(p):
        p = Gf.Vec3d(p)
        p[up] = 0
        return p
    for wall in iter_walls(stage):
        line = _line(wall)
        if not line:
            continue
        matrix = cache.GetLocalToWorldTransform(wall)
        for end, name in enumerate(JOIN_NAMES[:2]):
            point = plan(matrix.Transform(line[end]))
            for target in wall.GetRelationship("aeco:wall:" + name).GetTargets():
                peer = stage.GetPrimAtPath(target)
                if not peer or not peer.HasAPI("AecoWallAPI"):
                    continue
                footprint = _footprint(peer, cache, metres)
                if footprint is None:
                    continue
                vertices = list(map(plan, footprint))
                distance = min(_segment_distance(point, a, b) for a, b in
                               zip(vertices, vertices[1:] + vertices[:1])) * metres
                if distance > GEOMETRY_TOLERANCE:
                    issues.append(_issue("WallJoinedEndExtended", [wall, peer],
                        "%s differs from joined neighbour face by %.9g m" % (name, distance)))
    return issues


def _openings(stage, time_range):
    issues = []
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    metres = UsdGeom.GetStageMetersPerUnit(stage)
    for opening in stage.Traverse():
        if not opening.HasAPI("AecoOpeningAPI"):
            continue
        width = opening.GetAttribute("aeco:opening:width").Get()
        if width is None:
            continue
        matrix = cache.GetLocalToWorldTransform(opening)
        endpoints = [matrix.Transform(Gf.Vec3d(sign * width / (2 * metres), 0, 0)) for sign in (-1, 1)]
        for path in opening.GetRelationship("aeco:opening:host").GetTargets():
            wall = stage.GetPrimAtPath(path)
            if not wall or not wall.HasAPI("AecoWallAPI"):
                continue
            line = _line(wall)
            if line is None:
                continue
            wm = cache.GetLocalToWorldTransform(wall)
            start, end = map(wm.Transform, line)
            direction = end - start
            length = direction.GetLength()
            if length < 1e-12:
                continue
            direction /= length
            positions = [Gf.Dot(point - start, direction) * metres for point in endpoints]
            if min(positions) < -GEOMETRY_TOLERANCE or max(positions) > length * metres + GEOMETRY_TOLERANCE:
                issues.append(_issue("WallOpeningOutsideHost", [wall, opening],
                    "Opening width extends outside its wall axis span", True))
    return issues


def _size(prim, time_range):
    if not prim.HasAPI("AecoWallAPI") or not prim.HasAPI("AecoBuildUpAPI"):
        return []
    widths = prim.GetAttribute("aeco:buildUp:thicknesses").Get()
    attr = prim.GetAttribute("aeco:wall:thickness")
    value = attr.Get()
    if widths and value is not None and attr.HasAuthoredValueOpinion() and (
        not math.isfinite(value) or not math.isfinite(sum(widths)) or abs(value - sum(widths)) > SIZE_TOLERANCE):
        return [_issue("WallSizeMismatch", [prim], "Reported wall thickness differs from build-up sum")]
    return []


_RULES = (("WallKindMismatch", _kind, False, "Warn: wall classification mismatch."),
          ("WallMissingAxis", _axis, False, "Error: wall has no readable shared axis."),
          ("WallJoinAsymmetric", _joins, False, "Warn: joined wall does not list the source wall."),
          ("WallJoinedEndExtended", _extended, True, "Warn: joined end differs from neighbour face by more than 0.0001 m."),
          ("WallOpeningOutsideHost", _openings, True, "Error: opening extends outside the wall axis span."),
          ("WallSizeMismatch", _size, False, "Warn: wall thickness differs from build-up sum by more than 1e-8 m."))


def register():
    from . import register_plugins
    register_plugins()
    registry = UsdValidation.ValidationRegistry()
    metadata = registry.GetValidatorMetadataForKeyword(KEYWORD)
    return registry.GetOrLoadValidatorsByName([m.name for m in metadata])


def validate_stage(stage, include_core=False, include_builtin=True, include_buildup=True, profile=None):
    register()
    keywords = [KEYWORD]
    if include_buildup:
        from usdaeco_buildup import validators
        validators.register()
        keywords.append(validators.KEYWORD)
    if include_core:
        from usdaeco_tools import validators
        validators.register()
        keywords.append(validators.KEYWORD)
    if include_builtin and load_profile(profile).get("include_builtin", True):
        keywords.append("UsdCoreValidators")
    registry = UsdValidation.ValidationRegistry()
    names = [m.name for key in keywords for m in registry.GetValidatorMetadataForKeyword(key)]
    return apply_profile(list(UsdValidation.ValidationContext(registry.GetOrLoadValidatorsByName(names)).Validate(stage)), profile)


def split(issues):
    return ([e for e in issues if e.GetType() == UsdValidation.ValidationErrorType.Error],
            [e for e in issues if e.GetType() != UsdValidation.ValidationErrorType.Error])
