#!/usr/bin/env python3
"""Rebuild a deterministic semantic L/T corner with a hosted door."""
from pathlib import Path
import uuid
from pxr import Gf, Usd, UsdGeom, Vt
from usdaeco_wall import register_plugins


def build(output):
    register_plugins()
    stage = Usd.Stage.CreateInMemory()
    root = stage.DefinePrim('/WallCorner', 'Xform')
    stage.SetDefaultPrim(root)
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    UsdGeom.SetStageUpAxis(stage, 'Z')
    stage.SetMetadata('fallbackPrimTypes', {n: Vt.TokenArray(['Xform']) for n in ('AecoFacility', 'AecoLevel')})

    def identify(p, code, element=False):
        if element: p.ApplyAPI('AecoElementAPI')
        p.GetAttribute('aeco:id').Set(str(uuid.uuid5(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:usdaeco:id:v1'), str(p.GetPath()))))
        p.ApplyAPI('AecoClassificationAPI', 'ifc')
        p.GetAttribute('aeco:class:ifc:code').Set(code)

    facility = stage.DefinePrim('/WallCorner/Facility', 'AecoFacility')
    identify(facility, 'IfcBuilding')
    level = stage.DefinePrim('/WallCorner/Facility/Level', 'AecoLevel')
    identify(level, 'IfcBuildingStorey')
    level.GetAttribute('aeco:elevation').Set(0)
    stage.CreateClassPrim('/_TypeCatalog')
    catalog = stage.CreateClassPrim('/_TypeCatalog/LayeredWall')
    catalog.ApplyAPI('AecoTypeAPI'); catalog.ApplyAPI('AecoBuildUpAPI')
    for name, value in {'thicknesses': [0.02, 0.16, 0.02], 'functions': ['finish','structure','finish'],
                        'materials': ['Plaster','Masonry','Plaster'], 'priorities': [10,50,10],
                        'totalThickness': 0.2}.items():
        catalog.GetAttribute('aeco:buildUp:'+name).Set(value)
    walls = {}
    for name, start, end in [('Main',(0,0,0),(4,0,0)), ('Corner',(4,0,0),(4,3,0)),
                              ('Branch',(2,-2,0),(2,0,0))]:
        p = stage.DefinePrim(level.GetPath().AppendChild(name), 'Xform')
        p.GetInherits().AddInherit(catalog.GetPath())
        identify(p, 'IfcWall', True)
        p.ApplyAPI('AecoWallAPI'); p.ApplyAPI('AecoAxisAPI')
        # Local axis remains X-aligned; transforms exercise the validators.
        delta = Gf.Vec3d(*end) - Gf.Vec3d(*start)
        rotation = Gf.Rotation(Gf.Vec3d(1,0,0), delta.GetNormalized())
        matrix = Gf.Matrix4d(1); matrix.SetRotate(rotation); matrix.SetTranslateOnly(Gf.Vec3d(*start))
        UsdGeom.Xformable(p).MakeMatrixXform().Set(matrix)
        length = delta.GetLength()
        for n,v in {'start':(0,0,0),'end':(length,0,0),'length':length}.items(): p.GetAttribute('aeco:axis:'+n).Set(v)
        for n,v in {'height':3.0,'thickness':0.2,'locationLine':'finishFaceExterior',
                    'grossSideArea':length*3,'netSideArea':length*3-(1.89 if name=='Main' else 0),
                    'grossVolume':length*3*.2,'netVolume':(length*3-(1.89 if name=='Main' else 0))*.2}.items():
            p.GetAttribute('aeco:wall:'+n).Set(v)
        p.GetRelationship('aeco:wall:baseLevel').SetTargets([level.GetPath()])
        curve = UsdGeom.BasisCurves.Define(stage, p.GetPath().AppendChild('Axis'))
        curve.CreateTypeAttr('linear'); curve.CreateWrapAttr('nonperiodic')
        curve.CreatePointsAttr([(0,0,0),(length,0,0)]); curve.CreateCurveVertexCountsAttr([2])
        curve.CreateWidthsAttr([.01]); curve.SetWidthsInterpolation('constant'); curve.CreatePurposeAttr('guide')
        curve.GetPrim().ApplyAPI('AecoDerivedGeometryAPI')
        for n,v in {'source':p.GetAttribute('aeco:id').Get(),'role':'axis','approx':'exact','stamp':'wall example 0.1.0','tolerance':1e-9}.items():
            curve.GetPrim().GetAttribute('aeco:derived:'+n).Set(v)
        walls[name]=p
    for a,an,b,bn in [('Main','joinAtEnd','Corner','joinAtStart'),('Main','joinAlongPath','Branch','joinAtEnd')]:
        walls[a].GetRelationship('aeco:wall:'+an).AddTarget(walls[b].GetPath())
        walls[b].GetRelationship('aeco:wall:'+bn).AddTarget(walls[a].GetPath())
    door = stage.DefinePrim(level.GetPath().AppendChild('Door'), 'Xform')
    identify(door, 'IfcDoor', True)
    UsdGeom.Xformable(door).AddTranslateOp().Set((1,0.1,0))
    opening = stage.DefinePrim(walls['Main'].GetPath().AppendChild('Opening'), 'Xform')
    identify(opening, 'IfcOpeningElement', True)
    opening.ApplyAPI('AecoOpeningAPI')
    UsdGeom.Xformable(opening).AddTranslateOp().Set((1,0.1,0))
    for n,v in {'width':0.9,'height':2.1,'sillHeight':0}.items(): opening.GetAttribute('aeco:opening:'+n).Set(v)
    opening.GetRelationship('aeco:opening:host').SetTargets([walls['Main'].GetPath()])
    opening.GetRelationship('aeco:opening:filling').SetTargets([door.GetPath()])
    stage.GetRootLayer().Export(str(output))

if __name__ == '__main__':
    build(Path(__file__).resolve().parents[1] / 'usdAecoWall/examples/minimal.usda')
