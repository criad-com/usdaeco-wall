#!/pxrpythonsubst
"""Every declared error is exercised through the discovered Python plugin."""
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pxr import Plug, Sdf, Usd, UsdValidation
from usdaeco_wall import ROOT, register_plugins
from usdaeco_wall.validators import validate_stage

BASE = "/WallCorner/Facility/Level/"


def fixture():
    register_plugins()
    layer = Sdf.Layer.CreateAnonymous("wall-test.usda")
    layer.TransferContent(Sdf.Layer.FindOrOpen(str(ROOT / "usdAecoWall/examples/minimal.usda")))
    return Usd.Stage.Open(layer)


class TestValidators(unittest.TestCase):
    def setUp(self):
        register_plugins()
        Plug.Registry().RegisterPlugins(str(ROOT / "usdAecoWallValidators"))
        self.stage = fixture()
        self.wall = self.stage.GetPrimAtPath(BASE + "Main")

    def assertFinding(self, name, severity):
        found = [e for e in validate_stage(self.stage, include_buildup=False, include_builtin=False) if e.GetName() == name]
        self.assertTrue(found)
        self.assertTrue(all(e.GetType() == getattr(UsdValidation.ValidationErrorType, severity) for e in found))
        self.assertTrue(all(e.GetSites() and e.GetMessage() for e in found))

    def test_WallKindMismatch(self):
        self.wall.GetAttribute("aeco:class:ifc:code").Set("IfcSlab")
        self.assertFinding("WallKindMismatch", "Warn")

    def test_WallMissingAxis(self):
        self.wall.RemoveAPI("AecoAxisAPI")
        self.assertFinding("WallMissingAxis", "Error")

    def test_WallJoinAsymmetric(self):
        self.stage.GetPrimAtPath(BASE + "Corner").GetRelationship("aeco:wall:joinAtStart").SetTargets([])
        self.assertFinding("WallJoinAsymmetric", "Warn")

    def test_WallJoinedEndExtended(self):
        self.wall.GetAttribute("aeco:axis:end").Set((5, 0, 0))
        self.assertFinding("WallJoinedEndExtended", "Warn")

    def test_WallOpeningOutsideHost(self):
        self.wall.GetAttribute("aeco:axis:end").Set((0.8, 0, 0))
        self.assertFinding("WallOpeningOutsideHost", "Error")

    def test_WallSizeMismatch(self):
        self.wall.GetAttribute("aeco:wall:thickness").Set(0.25)
        self.assertFinding("WallSizeMismatch", "Warn")

    def test_clean_and_unrelated_prim(self):
        self.stage.DefinePrim("/Unrelated", "Mesh")
        self.assertEqual(validate_stage(self.stage, include_buildup=False, include_builtin=False), [])


if __name__ == "__main__":
    unittest.main()
