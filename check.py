#!/usr/bin/env python3
"""Wall acceptance: schema, promotion, example and raw lint; N checks, M failed."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'testenv')]
from usdaeco_wall import APIS, JOIN_NAMES, iter_walls, register_plugins, wall_type_of
E='/WallCorner/Facility/Level/'


def child(args, cwd=ROOT, extra_env=None):
    args=list(args)
    if args and args[0]=='-c': args[1]=textwrap.dedent(args[1])
    environment={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PXR_PLUGINPATH_NAME','PXR_AR_DEFAULT_SEARCH_PATH')}
    environment.update(extra_env or {})
    return subprocess.run([sys.executable,*map(str,args)],cwd=cwd,env=environment,text=True,capture_output=True,check=True)


def convert(source,destination):
    ifc_root = Path(os.environ.get('AECO_IFC_ROOT', ROOT.parent / 'usdaeco-ifc'))
    kit = Path(os.environ.get('TOOLCHAIN_DIR', ROOT.parent / 'usdaeco-toolchain'))
    from usdaeco_wall import plugin_paths
    code="import runpy,sys; sys.path[:0]=[sys.argv.pop(1),sys.argv.pop(1)]; runpy.run_module('usdaeco_ifc.convert',run_name='__main__')"
    child(['-c',code,ifc_root/'tools',kit/'tools',source,'-o',destination],
          extra_env={'PXR_PLUGINPATH_NAME': os.pathsep.join(map(str,plugin_paths()[:2]))})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--without-importer', action='store_true', help='Explicit USD-only gate for environments without IfcOpenShell')
    parser.add_argument('--report',type=Path)
    parser.add_argument('--core-plugin')
    parser.add_argument('--plugin')
    parser.add_argument("--profile", type=Path, default=ROOT / "conformance/profiles/wall.json",
                        help="Severity overlay for example conformance; seeded contract probes retain default grades")
    args=parser.parse_args()
    if args.without_importer and args.baseline: parser.error('--baseline requires importer checks')
    if args.core_plugin: os.environ['CORE_PLUGIN_DIR']=args.core_plugin
    if args.plugin: os.environ['WALL_PLUGIN_DIR']=args.plugin
    print('== stage: wall registry and inherited checks', flush=True)
    register_plugins()
    from usdaeco_buildup import core_root, layers_of
    sys.path.insert(0,str(core_root()/'tools'))
    from pxr import Gf, Plug, Sdf, Usd, UsdGeom, UsdValidation
    from usdaeco_check import Report, can_apply, link_check, plugin_requires, registry_probe, term_sweep, validate_examples
    from usdaeco_check.plugins import check_requirements
    from usdaeco_wall import validators
    report=Report(); imports={}
    # Core validation is required evidence; an unavailable plugin is fatal.
    import usdAecoValidators
    core_registry = UsdValidation.ValidationRegistry()
    core_metadata = core_registry.GetValidatorMetadataForKeyword('UsdAecoValidators')
    core_validators = [core_registry.GetOrLoadValidatorByName(m.name) for m in core_metadata]
    if len(core_validators) != 8 or not all(core_validators):
        raise RuntimeError('usdAecoValidators must load all eight core validators')
    report.check('core validators loaded through UsdValidation', True, '8/8 loaded')
    profiled = validators.validate_stage(Usd.Stage.Open(str(ROOT/'usdAecoWall/examples/minimal.usda')), include_core=True, profile=args.profile)
    report.check('profile example conformance', not validators.split(profiled)[0])

    if not report.run('plugin requirements', plugin_requires):
        return report.finish()
    report.add(registry_probe([*APIS,'AecoBuildUpAPI','AecoAxisAPI']))
    plugin=Plug.Registry().GetPluginWithName('usdAecoWall')
    manifest=json.loads((ROOT/'library.json').read_text())
    report.check('codeless manifest with three dependencies',plugin.isResource and plugin.name==manifest['name'] and
        plugin.metadata['aeco']=={key:manifest[key] for key in ('version','tier','requires')})
    report.add(can_apply([(typ,api,want) for api in APIS for typ,want in
        [('Xform',True),('Mesh',True),('Scope',True),('AecoSystem',False),('Material',False)]]))
    definitions=[Usd.SchemaRegistry().FindAppliedAPIPrimDefinition(api) for api in APIS]
    properties={n:d for d in definitions for n in d.GetPropertyNames()}
    derived={'aeco:wall:'+n for n in ('thickness','grossSideArea','netSideArea','grossVolume','netVolume')}
    report.check('27 properties; five derived flags; conditional height unflagged',len(properties)==27 and
        {n for n,d in properties.items() if d.GetPropertyMetadata(n,'aecoDerived')}==derived)
    source=Sdf.Layer.FindOrOpen(str(ROOT/'usdAecoWall/schema.usda'))
    report.check('every property documented; build-up schema sublayered',
        all(p.documentation for api in APIS for p in source.GetPrimAtPath('/'+api).properties)
        and 'usdAecoBuildUp/schema.usda' in source.subLayerPaths)
    report.check('joins are relationships; E6 port graph unchanged',all(
        definitions[0].GetSchemaRelationshipSpec('aeco:wall:'+n) for n in JOIN_NAMES))
    validators.register(); validators.register()
    report.check('six validators registered idempotently',len(UsdValidation.ValidationRegistry().GetValidatorMetadataForKeyword(validators.KEYWORD))==6)
    report.add(validate_examples(ROOT/'usdAecoWall/examples',[],validators=[lambda s: validators.validate_stage(s,include_core=True,include_builtin=False)]))
    def fresh():
        layer=Sdf.Layer.CreateAnonymous('example.usda')
        layer.TransferContent(Sdf.Layer.FindOrOpen(str(ROOT/'usdAecoWall/examples/minimal.usda')))
        return Usd.Stage.Open(layer)
    def findings(s):
        return Counter((e.GetName(),str(e.GetType()).rsplit('.',1)[-1]) for e in validators.validate_stage(s,include_builtin=False))
    core_seed = fresh()
    core_seed.GetPrimAtPath(E+'Main').GetAttribute('aeco:id').Set('')
    core_errors = UsdValidation.ValidationContext(core_validators).Validate(core_seed)
    report.check('core validators detect seeded missing identity', any(
        e.GetName() == 'missingId' and e.GetType() == UsdValidation.ValidationErrorType.Error
        for e in core_errors))
    s=fresh(); walls=list(iter_walls(s))
    report.check('example has L/T joins, door and inherited three-layer catalog',len(walls)==3 and
        all(len(layers_of(wall_type_of(p)))==3 for p in walls) and
        len(s.GetPrimAtPath(E+'Main').GetRelationship('aeco:wall:joinAlongPath').GetTargets())==1 and
        s.GetPrimAtPath(E+'Main/Opening').GetRelationship('aeco:opening:filling').GetTargets()==[Sdf.Path(E+'Door')])
    report.check('example has zero errors and zero warnings',not findings(s))
    seeds=[('WallKindMismatch','Warn',lambda s:s.GetPrimAtPath(E+'Main').GetAttribute('aeco:class:ifc:code').Set('IfcSlab')),
        ('WallMissingAxis','Error',lambda s:s.GetPrimAtPath(E+'Main').RemoveAPI('AecoAxisAPI')),
        ('WallJoinAsymmetric','Warn',lambda s:s.GetPrimAtPath(E+'Corner').GetRelationship('aeco:wall:joinAtStart').SetTargets([])),
        ('WallJoinedEndExtended','Warn',lambda s:s.GetPrimAtPath(E+'Main').GetAttribute('aeco:axis:end').Set((4.5,0,0))),
        ('WallOpeningOutsideHost','Error',lambda s:s.GetPrimAtPath(E+'Main').GetAttribute('aeco:axis:end').Set((.8,0,0))),
        ('WallSizeMismatch','Warn',lambda s:s.GetPrimAtPath(E+'Main').GetAttribute('aeco:wall:thickness').Set(.3))]
    for name,severity,edit in seeds:
        s=fresh(); edit(s); result=findings(s)
        report.check('seed '+name+' detected as '+severity,(name,severity) in result,str(dict(result)))
    s=fresh(); s.GetPrimAtPath(E+'Main/Opening').GetAttribute('aeco:opening:width').Set(2.2)
    report.check('opening width crossing start caught despite origin inside',('WallOpeningOutsideHost','Error') in findings(s))
    s=fresh(); s.GetPrimAtPath(E+'Main').GetAttribute('aeco:axis:end').Set((4.00005,0,0))
    report.check('joined-face tolerance avoids small numerical warnings',('WallJoinedEndExtended','Warn') not in findings(s))
    s=fresh(); UsdGeom.Xformable(s.GetPrimAtPath('/WallCorner')).AddTranslateOp().Set((100,200,10))
    UsdGeom.Xformable(s.GetPrimAtPath('/WallCorner')).AddRotateZOp().Set(37)
    report.check('geometry validators invariant under parent rigid transform',not findings(s))
    refused=[]
    core={'version':'0.9.1','tier':'core','requires':{}}
    axis={'version':'0.1.0','tier':'section','requires':{'usdAeco':'>=0.9,<1.0'}}
    for buildup in (None,{'version':'0.0.9','tier':'section','requires':{'usdAeco':'>=0.9'}}):
        metadata={'usdAeco':core,'usdAecoAxis':axis,'usdAecoWall':plugin.metadata['aeco']}
        if buildup: metadata['usdAecoBuildUp']=buildup
        try:check_requirements(metadata)
        except ValueError:refused.append(True)
        else:refused.append(False)
    report.check('missing and old build-up refused',all(refused))
    probe=child(['-c','''
import json,sys
from pxr import Plug,Usd,UsdGeom
assert not any(p.name.startswith('usdAeco') for p in Plug.Registry().GetAllPlugins())
s=Usd.Stage.Open(sys.argv[1]); assert s and not s.GetCompositionErrors()
assert s.GetPrimAtPath('/WallCorner/Facility/Level').IsA(UsdGeom.Xform)
p=s.GetPrimAtPath('/WallCorner/Facility/Level/Main')
assert p.GetAttribute('aeco:wall:thickness').Get()==.2
assert list(p.GetAttribute('aeco:buildUp:thicknesses').Get())==[.02,.16,.02]
assert len(p.GetRelationship('aeco:wall:joinAtEnd').GetTargets())==1
assert not any(p.name.startswith('usdAeco') for p in Plug.Registry().GetAllPlugins())
transforms={str(p.GetPath()):[float(v) for row in UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default()) for v in row]
            for p in s.Traverse() if UsdGeom.Xformable(p)}
print(json.dumps(transforms))
''',ROOT/'usdAecoWall/examples/minimal.usda'])
    s=fresh()
    transforms={str(p.GetPath()):[float(v) for row in UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default()) for v in row]
                for p in s.Traverse() if UsdGeom.Xformable(p)}
    report.check('vanilla example probe',json.loads(probe.stdout)==transforms,
        '%d world transforms identical; no family plugins; fallbacks, inherited section and joins readable'%len(transforms))
    if not args.without_importer:
        print('== stage: inherited IFC importer checks', flush=True)
        from usdaeco_wall.importer import import_wall
        from fixtures import build_baseline
        with tempfile.TemporaryDirectory(prefix='wall-check-') as temporary:
            tmp=Path(temporary)
            for fixture,mm in [('metres',False),('millimetres',True)]:
                src=tmp/(fixture+'.ifc'); corepath=tmp/(fixture+'.usda'); out=tmp/(fixture+'-kind.usda')
                build_baseline(src,millimetres=mm); convert(src,corepath)
                before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [src,*tmp.glob(fixture+'*.usda')]}
                stats=import_wall(corepath,src,out); imports[fixture]=stats
                s=Usd.Stage.Open(str(out)); walls=list(iter_walls(s))
                report.check(fixture+' importer APIs, axis reuse and reciprocal joins',stats['AecoWallAPI']==2 and stats['AecoBuildUpAPI']==1 and
                    stats['AecoOpeningAPI']==1 and stats['fillings']==1 and stats['axesReused']==2 and stats['joinTargets']==2 and stats['missingAxes']==0,
                    json.dumps(stats,sort_keys=True))
                errors,warnings=validators.split(validators.validate_stage(s,include_core=True))
                report.check(fixture+' imported stage validates',not errors and not warnings,
                    '; '.join(e.GetName()+': '+e.GetMessage() for e in errors+warnings) or '0 errors, 0 warnings')
                report.check(fixture+' SI dimensions and property promotion',all(
                    abs(p.GetAttribute('aeco:wall:thickness').Get()-.2)<1e-10 and
                    abs(p.GetAttribute('aeco:wall:height').Get()-3)<1e-10 and
                    p.GetAttribute('aeco:wall:isExternal').Get() is True and
                    p.GetAttribute('aeco:props:Pset_WallCommon:IsExternal').Get() is None and
                    p.GetAttribute('aeco:props:Pset_WallCommon:Reference').Get()=='Retain this field' for p in walls))
                report.check(fixture+' input files unchanged and no axis opinions in kind',all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in before.items()) and
                    'aeco:axis:' not in out.read_text())
                openings=[p for p in s.Traverse() if p.HasAPI('AecoOpeningAPI')]
                report.check(fixture+' opening dimensions and placement',len(openings)==1 and abs(openings[0].GetAttribute('aeco:opening:width').Get()-.9)<1e-8 and
                    abs(UsdGeom.XformCache().GetLocalToWorldTransform(openings[0]).ExtractTranslation()[0]-1)<1e-8)
                report.check(fixture+' promoted net and gross quantities', sorted(round(p.GetAttribute('aeco:wall:netSideArea').Get(),6) for p in walls)==[9.0,10.11]
                    and sorted(round(p.GetAttribute('aeco:wall:netVolume').Get(),6) for p in walls)==[1.8,2.022])
                # Removing the overlay recovers the original stage, including
                # raw property-set values and unchanged geometry/transform opinions.
                original=Usd.Stage.Open(str(corepath))
                wrapper=Usd.Stage.CreateInMemory(); wrapper.GetRootLayer().subLayerPaths=[str(out),str(corepath)]
                # Stage-level metadata belongs on the session root; USD does not
                # compose metersPerUnit/upAxis/defaultPrim from sublayers.
                for key in ('defaultPrim','upAxis','metersPerUnit','fallbackPrimTypes'):
                    if original.HasAuthoredMetadata(key): wrapper.SetMetadata(key,original.GetMetadata(key))
                wrapper.MuteLayer(str(out))
                muted,base=wrapper.Flatten(),original.Flatten()
                muted.documentation=''; base.documentation=''
                report.check(fixture+' muting kind recovers core composition',muted.ExportToString()==base.ExportToString())
                if not mm:
                    report.check('new output refusal',_refuses(lambda:import_wall(corepath,src,out)))
                    vanilla=child(['-c', '''
    import sys
    from pxr import Plug,Usd
    s=Usd.Stage.Open(sys.argv[1]); assert s and not s.GetCompositionErrors()
    assert not any(p.name.startswith('usdAeco') for p in Plug.Registry().GetAllPlugins())
    assert sum(bool(p.GetRelationship('aeco:opening:host').GetTargets()) for p in s.Traverse())==1
    print('imported layered stage composes without plugins')
    ''',out])
                    report.check('vanilla importer probe',True,vanilla.stdout.strip())
                    cli=child([ROOT/'tools/aeco-wall-import',corepath,src,'-o',tmp/'cli-kind.usda'])
                    report.check('aeco-wall-import CLI',json.loads(cli.stdout)==stats)
                    import ifcopenshell
                    import ifcopenshell.util.element as element
                    model=ifcopenshell.open(str(src))
                    wall=model.by_type('IfcWall')[0]
                    usage=element.get_material(wall)
                    layers=usage.ForLayerSet.MaterialLayers
                    layers[1].LayerThickness=.15; layers[2].LayerThickness=.03
                    # Asymmetric finish widths distinguish all six reference lines.
                    expected={'centerline':.1,'coreCenterline':.095,'finishFaceExterior':0.,
                              'finishFaceInterior':.2,'coreFaceExterior':.02,'coreFaceInterior':.17}
                    uid=str(__import__('uuid').UUID(hex=ifcopenshell.guid.expand(wall.GlobalId)))
                    matches=[]
                    for flipped in (False,True):
                        usage.DirectionSense='NEGATIVE' if flipped else 'POSITIVE'
                        for token,reference in expected.items():
                            usage.OffsetFromReferenceLine=reference if flipped else -reference
                            variant=tmp/('usage-'+token+str(flipped)+'.ifc'); model.write(str(variant))
                            destination=variant.with_suffix('.usda')
                            import_wall(corepath,variant,destination)
                            composed=Usd.Stage.Open(str(destination))
                            p=next(p for p in iter_walls(composed) if p.GetAttribute('aeco:id').Get()==uid)
                            matches.append(p.GetAttribute('aeco:wall:locationLine').Get()==token and
                                           p.GetAttribute('aeco:wall:flipped').Get()==flipped)
                    report.check('all six location lines in both direction senses',all(matches),'12 IFC usage mappings')
                    usage.OffsetFromReferenceLine=.12345
                    variant=tmp/'unsupported.ifc';model.write(str(variant))
                    destination=tmp/'unsupported.usda'; result=import_wall(corepath,variant,destination)
                    composed=Usd.Stage.Open(str(destination));p=next(p for p in iter_walls(composed) if p.GetAttribute('aeco:id').Get()==uid)
                    report.check('arbitrary usage offset blocked and counted',result['unsupportedLocationLines']==1 and p.GetAttribute('aeco:wall:locationLine').Get() is None)
            if args.baseline:
                corepath=tmp/'external.usda'; out=tmp/'external-kind.usda'
                convert(args.baseline.resolve(),corepath)
                stats=import_wall(corepath,args.baseline,out); imports['baseline']=stats
                s=Usd.Stage.Open(str(out)); result=findings(s)
                report.check('reference baseline joins both ways',stats['AecoWallAPI']==2 and stats['AecoBuildUpAPI']==2 and stats['axesReused']==2 and stats['joinTargets']==2 and
                    ('WallJoinAsymmetric','Warn') not in result,json.dumps(stats,sort_keys=True))
                errors,warnings=validators.split(validators.validate_stage(s,include_core=True))
                report.check('reference baseline validates',not errors,'errors=%d warnings=%d'%(len(errors),len(warnings)))
    print('== stage: source contracts and published example', flush=True)
    from testUsdAecoWallSchema import previous_contract, schema_contract
    report.check('schema unchanged from v0.1.2 via Sdf', schema_contract(source)==previous_contract(),
                 '27 property names, types, defaults, variability, custom flags, allowed tokens and derived flags')
    metadata = UsdValidation.ValidationRegistry().GetValidatorMetadataForKeyword(validators.KEYWORD)
    report.check('validator listing uses plugin names and schema types',
                 len(metadata)==6 and all(m.name.startswith('usdAecoWallValidators:') and m.name.endswith('Checker')
                 and UsdValidation.ValidationRegistry().GetOrLoadValidatorByName(m.name) for m in metadata))
    from usdaeco_check.example import check_example
    report.add(check_example(ROOT/'examples/datacentre'))
    example_out = ROOT/'examples/datacentre/out'
    if (example_out/'manifest.json').exists():
        from usdaeco_wall.example import published_source, source_counts, office_walls
        from usdaeco_wall.stage_import import classified_walls
        published, published_manifest = published_source()
        original = Usd.Stage.Open(str(published))
        promoted = Usd.Stage.Open(str(example_out/'wall.drivers.usda'))
        composed = Usd.Stage.Open(str(example_out/'example.usda'))
        run_manifest = json.loads((example_out/'manifest.json').read_text())
        report.check('example source is pinned clash release', run_manifest['source']['mode']=='pinned' and
                     run_manifest['datacentre']=={'ref':json.loads((ROOT/'dependencies.json').read_text())['repos']['datacentre']['ref'],'variant':'clash'})
        report.check('published census and promotion coverage', source_counts(original)==published_manifest['counts'] and
                     len(list(iter_walls(promoted)))==len(classified_walls(original)), str(len(classified_walls(original)))+' walls')
        wall_layer = Sdf.Layer.FindOrOpen(str(example_out/'wall.drivers.usda'))
        quantity_layer = Sdf.Layer.FindOrOpen(str(example_out/'wall.drivers.derived.usda'))
        paths=[]
        wall_layer.Traverse(Sdf.Path.absoluteRootPath, lambda p: paths.append(p) if p.IsPropertyPath() else None)
        report.check('stage importer separates drivers and derived quantities',
                     all(promoted.GetPropertyAtPath(p).GetMetadata('aecoDerived') is not True for p in paths) and
                     bool(quantity_layer.rootPrims))
        body_paths=[p.GetPath() for p in original.Traverse() if p.IsA(UsdGeom.Mesh)]
        report.check('promotion preserves all published mesh topology and transforms', all(
            original.GetPrimAtPath(p).GetAttribute(n).Get()==promoted.GetPrimAtPath(p).GetAttribute(n).Get()
            for p in body_paths for n in ('points','faceVertexCounts','faceVertexIndices')) and all(
                UsdGeom.Xformable(original.GetPrimAtPath(p)).ComputeLocalToWorldTransform(Usd.TimeCode.Default())==
                UsdGeom.Xformable(promoted.GetPrimAtPath(p)).ComputeLocalToWorldTransform(Usd.TimeCode.Default()) for p in body_paths),
                str(len(body_paths))+' meshes unchanged')
        guides=[p for p in composed.Traverse() if p.IsA(UsdGeom.BasisCurves) and p.GetAttribute('aeco:derived:stamp').Get()=='aeco-axis 0.1.3']
        report.check('office wall axes only in dedicated derivation',len(guides)==len(office_walls(promoted)) and
                     all(p.GetParent().HasAPI('AecoWallAPI') and p.GetAttribute('purpose').Get()=='guide' for p in guides))
        extent=[p for p in composed.Traverse() if p.GetAttribute('aeco:derived:role').Get()=='extent']
        report.check('review excludes every extent guide and requests all purposes',bool(extent) and
                     all(UsdGeom.Imageable(p).ComputeVisibility()=='invisible' for p in extent) and
                     run_manifest['render_purposes']==['guide','proxy','render'])
        vanilla=child(['-c', '''
from pxr import Plug,Usd,UsdGeom
import sys,json
s=Usd.Stage.Open(sys.argv[1]); assert s and not s.GetCompositionErrors()
assert not any(p.name.startswith('usdAeco') for p in Plug.Registry().GetAllPlugins())
fallbacks=s.GetMetadata('fallbackPrimTypes')
assert all(p.GetTypeName() in fallbacks for p in s.Traverse() if p.GetTypeName().startswith('Aeco'))
print(json.dumps({'meshes':sum(p.IsA(UsdGeom.Mesh) for p in s.Traverse()),'axes':sum(p.IsA(UsdGeom.BasisCurves) for p in s.Traverse())}))
''',example_out/'example.usda'])
        report.check('published example composes plugin-free',json.loads(vanilla.stdout)=={'meshes':len(body_paths),'axes':len(guides)})
    report.add(link_check(ROOT/'README.md')); report.add(link_check(ROOT/'docs')); report.add(link_check(ROOT/'examples'))
    report.add(term_sweep([ROOT/n for n in ('usdAecoWall','usdAecoWallValidators','tools','docs','examples','README.md','check.py','flake.nix','dependencies.json')],
        [r'\b(?:10\.\d{1,3}|192\.168)\.\d{1,3}\.\d{1,3}\b',r'[/]Volumes[/]']))
    behavioral = {'checks': len(report.results), 'failed': report.failed}
    print('== stage: raw structure lint', flush=True)
    from usdaeco_check.structure import check_structure
    from usdaeco_wall import plugin_paths
    structure = check_structure(ROOT, deps=plugin_paths()[:3])
    for result in structure:
        report.add(result)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        # Reports may be shared; diagnostics should not expose checkout paths.
        data={'checks':[asdict(r) for r in report.results],'failed':report.failed,'importer':imports,'behavioral':behavioral,
              'structure':{'checks':len(structure),'failed':sum(not r.ok for r in structure)}}
        encoded=json.dumps(data,indent=2).replace(str(ROOT),'<repo>').replace(str(ROOT.parent),'<siblings>')
        args.report.write_text(encoded+'\n')
    return report.finish()


def _refuses(callback):
    try:callback()
    except ValueError:return True
    return False

if __name__=='__main__':raise SystemExit(main())
