"""Published-USD promotion is sparse, deterministic and honest about gaps."""
import pytest
from pxr import Sdf, Usd
from usdaeco_wall import register_plugins
from usdaeco_wall.stage_import import import_stage


@pytest.fixture
def source(tmp_path):
    register_plugins()
    path = tmp_path / "source.usda"
    stage = Usd.Stage.CreateNew(str(path))
    stage.SetMetadata("metersPerUnit", 1.0)
    wall = stage.DefinePrim("/Wall", "Xform")
    for api in ("AecoElementAPI", "AecoAxisAPI"):
        wall.ApplyAPI(api)
    wall.ApplyAPI("AecoClassificationAPI", "ifc")
    wall.GetAttribute("aeco:id").Set("270af0ce-1e18-40bd-b0b4-21cf56d358c0")
    wall.GetAttribute("aeco:class:ifc:code").Set("IfcWall.PARTITIONING")
    wall.GetAttribute("aeco:axis:start").Set((0, 0, 0))
    wall.GetAttribute("aeco:axis:end").Set((4, 0, 0))
    for key, value in {"Width": 0.15, "Height": 3.0, "GrossVolume": 1.8}.items():
        wall.CreateAttribute("aeco:props:Qto_WallBaseQuantities:" + key, Sdf.ValueTypeNames.Double).Set(value)
    catalog = stage.CreateClassPrim("/Catalog/WallType")
    catalog.ApplyAPI("AecoTypeAPI")
    wall.GetInherits().AddInherit(catalog.GetPath())
    stage.GetRootLayer().Save()
    return path


def test_sparse_layers_and_source_unchanged(source, tmp_path):
    before = source.read_bytes()
    output = tmp_path / "wall.usda"
    stats = import_stage(source, output)
    assert source.read_bytes() == before
    assert stats["AecoWallAPI"] == stats["AecoBuildUpAPI"] == 1
    assert stats["AecoOpeningAPI"] == stats["joinTargets"] == 0
    driver = Sdf.Layer.FindOrOpen(str(output))
    quantities = Sdf.Layer.FindOrOpen(str(tmp_path / "wall.derived.usda"))
    assert not driver.GetPropertyAtPath("/Wall.aeco:wall:thickness")
    assert quantities.GetPropertyAtPath("/Wall.aeco:wall:thickness").default == 0.15
    assert not quantities.GetPropertyAtPath("/Wall.aeco:wall:height")
    composed = Usd.Stage.Open(str(output))
    wall = composed.GetPrimAtPath("/Wall")
    assert wall.GetAttribute("aeco:wall:thickness").Get() == 0.15
    assert wall.GetAttribute("aeco:wall:height").Get() == 3.0
    assert wall.GetAttribute("aeco:wall:locationLine").Get() is None
    assert wall.GetAttribute("aeco:props:Qto_WallBaseQuantities:Width").Get() is None
    assert wall.GetAttribute("aeco:buildUp:functions").Get() == ["other"]
    assert not any("aeco:axis:" in p.name for p in driver.GetPrimAtPath("/Wall").properties)


@pytest.mark.parametrize("value", [-1.0, 0.0, float("nan"), float("inf")])
def test_invalid_width_fails_before_writing(source, tmp_path, value):
    stage = Usd.Stage.Open(str(source))
    stage.GetPrimAtPath("/Wall").GetAttribute("aeco:props:Qto_WallBaseQuantities:Width").Set(value)
    stage.GetRootLayer().Save()
    output = tmp_path / "wall.usda"
    with pytest.raises(ValueError, match="Invalid SI quantity"):
        import_stage(source, output)
    assert not output.exists() and not output.with_name("wall.derived.usda").exists()


def test_missing_width_is_counted(source, tmp_path):
    stage = Usd.Stage.Open(str(source))
    stage.GetPrimAtPath("/Wall").RemoveProperty("aeco:props:Qto_WallBaseQuantities:Width")
    stage.GetRootLayer().Save()
    result = import_stage(source, tmp_path / "wall.usda")
    assert result["missingWidths"] == 1 and result["AecoBuildUpAPI"] == 0


def test_existing_output_refused(source, tmp_path):
    target = tmp_path / "wall.usda"
    target.write_text("retain this file")
    with pytest.raises(ValueError):
        import_stage(source, target)
    assert target.read_text() == "retain this file"


def test_type_width_conflict_refused(source, tmp_path):
    stage = Usd.Stage.Open(str(source))
    Sdf.CopySpec(stage.GetRootLayer(), "/Wall", stage.GetRootLayer(), "/Second")
    second = stage.GetPrimAtPath("/Second")
    second.GetAttribute("aeco:id").Set("d5e67f58-025f-470c-bb64-23560e5480de")
    second.GetAttribute("aeco:props:Qto_WallBaseQuantities:Width").Set(0.2)
    stage.GetRootLayer().Save()
    with pytest.raises(ValueError, match="Conflicting widths"):
        import_stage(source, tmp_path / "wall.usda")


def test_legacy_profile_error_alias():
    from usdaeco_wall.profiles import load_profile
    assert load_profile({"severity_overrides": {"wallMissingAxis": "info"}})["severity_overrides"] == {"WallMissingAxis": "info"}
    with pytest.raises(ValueError, match="Conflicting severity"):
        load_profile({"severity_overrides": {"wallMissingAxis": "info", "WallMissingAxis": "error"}})


def test_stage_cli_does_not_import_ifcopenshell(source, tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    code = '''
import sys, importlib.abc
sys.path.insert(0, sys.argv.pop(1))
class NoIfc(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('ifcopenshell'):
            raise AssertionError('stage-only promotion must not import IFC')
sys.meta_path.insert(0, NoIfc())
from usdaeco_wall.cli import main
raise SystemExit(main())
'''
    result = subprocess.run([sys.executable, '-c', code, str(root / 'tools'), 'import', str(source),
                             '--out', str(tmp_path / 'cli.usda')], text=True, capture_output=True,
                            env={k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PXR_PLUGINPATH_NAME')})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'cli.derived.usda').is_file()
