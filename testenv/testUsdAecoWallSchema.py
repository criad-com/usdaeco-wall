#!/pxrpythonsubst
"""The migration preserves the published schema's complete property contract."""
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from usdaeco_wall import APIS, ROOT, register_plugins
from pxr import Plug, Sdf, Usd


def schema_contract(layer):
    return {name: {p.name: (str(p.typeName) if isinstance(p, Sdf.AttributeSpec) else "relationship",
                           str(p.default) if isinstance(p, Sdf.AttributeSpec) else None,
                           str(p.variability), p.custom,
                           p.GetInfo("aecoDerived") if p.HasInfo("aecoDerived") else None,
                           str(p.GetInfo("allowedTokens")) if p.HasInfo("allowedTokens") else None)
                   for p in layer.GetPrimAtPath("/" + name).properties} for name in APIS}


def previous_contract():
    import hashlib, json
    snapshot = ROOT / "testenv/baseline/schema-v0.1.2.usda"
    manifest = json.loads(snapshot.with_name("manifest.json").read_text())
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == manifest["sha256"]
    text = snapshot.read_text()
    if (ROOT / ".git").exists():
        tagged = subprocess.check_output(["git", "show", manifest["ref"] + ":" + manifest["path"]], cwd=ROOT, text=True)
        assert tagged == text
    previous = Sdf.Layer.CreateAnonymous("previous.usda")
    previous.ImportFromString(text)
    return schema_contract(previous)


class TestSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        register_plugins()
        Plug.Registry().RegisterPlugins(str(ROOT / "usdAecoWall"))

    def test_previous_tag_property_contract(self):
        current = Sdf.Layer.FindOrOpen(str(ROOT / "usdAecoWall/schema.usda"))
        self.assertEqual(schema_contract(current), previous_contract())
        self.assertEqual(sum(map(len, schema_contract(current).values())), 27)

    def test_opening_remains_in_wall(self):
        self.assertIsNotNone(Usd.SchemaRegistry().FindAppliedAPIPrimDefinition("AecoOpeningAPI"))
        self.assertEqual(Usd.SchemaRegistry().FindAppliedAPIPrimDefinition("AecoOpeningAPI").GetPropertyNames(),
                         ["aeco:opening:filling", "aeco:opening:height", "aeco:opening:host", "aeco:opening:sillHeight", "aeco:opening:width"])


if __name__ == "__main__":
    unittest.main()
