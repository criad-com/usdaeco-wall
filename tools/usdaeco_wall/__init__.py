"""Queries and registration for the codeless wall and opening APIs."""
import os
from pathlib import Path
import sys

__version__ = "0.2.4"
ROOT = Path(__file__).resolve().parents[2]
APIS = ("AecoWallAPI", "AecoOpeningAPI")
JOIN_NAMES = ("joinAtStart", "joinAtEnd", "joinAlongPath")
SIZE_TOLERANCE = 1e-8  # SI metres
GEOMETRY_TOLERANCE = 1e-4  # SI metres


def buildup_root():
    return Path(os.environ.get("AECO_BUILDUP_ROOT", ROOT.parent / "usdaeco-buildup"))


def register_plugins(plugin_dir=None):
    """Register core first and the complete closure before the USD registry."""
    kit = Path(os.environ.get("TOOLCHAIN_DIR", ROOT.parent / "usdaeco-toolchain"))
    core = Path(os.environ.get("AECO_CORE_ROOT", ROOT.parent / "usdaeco-core"))
    axis = Path(os.environ.get("AECO_AXIS_ROOT", ROOT.parent / "usdaeco-axis"))
    for root in (ROOT, kit, core, axis, buildup_root()):
        for path in (root, root / "tools", root / "python"):
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
    from usdaeco_check import plugin_requires
    from pxr import Plug, Usd
    paths = plugin_paths(plugin_dir)
    result = plugin_requires(paths)
    if not result:
        raise RuntimeError(result.detail)
    for root, name in ((core, "usdAeco"), (axis, "usdAecoAxis"),
                       (buildup_root(), "usdAecoBuildUp"), (ROOT, "usdAecoWall")):
        for path in (root / (name + "Validators"), root / "python" / (name + "Validators")):
            if path.is_dir():
                Plug.Registry().RegisterPlugins(str(path))
    if any(Usd.SchemaRegistry().FindAppliedAPIPrimDefinition(api) is None for api in APIS):
        raise RuntimeError("Register the complete plugin closure before opening the first stage; restart this process")
    return Plug.Registry().GetPluginWithName("usdAecoWall")


def plugin_paths(plugin_dir=None):
    """Accept installed resource dirs and both generations of source layout."""
    paths = []
    for variable, root, library in (
        ("CORE_PLUGIN_DIR", Path(os.environ.get("AECO_CORE_ROOT", ROOT.parent / "usdaeco-core")), "usdAeco"),
        ("AXIS_PLUGIN_DIR", Path(os.environ.get("AECO_AXIS_ROOT", ROOT.parent / "usdaeco-axis")), "usdAecoAxis"),
        ("BUILDUP_PLUGIN_DIR", buildup_root(), "usdAecoBuildUp"),
        ("WALL_PLUGIN_DIR", ROOT, "usdAecoWall"),
    ):
        override = plugin_dir if variable == "WALL_PLUGIN_DIR" and plugin_dir else os.environ.get(variable)
        candidates = [root / "out/plugins" / library / "resources", root / "plugins" / library / "resources", root / library]
        if variable == "WALL_PLUGIN_DIR":
            candidates.insert(0, root / library)
        if override:
            candidates = [Path(override)]
        paths.append(next((p for p in candidates if (p / "plugInfo.json").is_file()), candidates[0]))
    return paths


def iter_walls(stage):
    return (p for p in stage.Traverse() if p.HasAPI("AecoWallAPI"))


def wall_type_of(prim):
    if not prim:
        return None
    if prim.IsAbstract() and prim.HasAPI("AecoBuildUpAPI"):
        return prim
    for path in prim.GetInherits().GetAllDirectInherits():
        candidate = prim.GetStage().GetPrimAtPath(path)
        if candidate and candidate.IsAbstract() and candidate.HasAPI("AecoBuildUpAPI"):
            return candidate
    return None


def section_offsets(thicknesses, functions):
    """Reference position from the first layer face, before flip, in metres.

    Structure layers bound the core. A section without structure uses the
    whole section as its core. IFC categories cannot encode core boundaries
    separately; consumers must preserve that limitation.
    """
    total = sum(thicknesses)
    structural = [i for i, f in enumerate(functions) if f == "structure"]
    first = sum(thicknesses[:structural[0]]) if structural else 0.0
    last = sum(thicknesses[:structural[-1] + 1]) if structural else total
    return {"centerline": total / 2, "coreCenterline": (first + last) / 2,
            "finishFaceExterior": 0.0, "finishFaceInterior": total,
            "coreFaceExterior": first, "coreFaceInterior": last}
