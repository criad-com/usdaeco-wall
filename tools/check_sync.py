#!/usr/bin/env python3
"""Optional integration gate: real kind importers -> existing sync wall cases.

Uses sibling sync, pipe, build-up, core and toolchain checkouts. No prototype
schema or session kind importer participates. All models live in a temporary
workspace. The default gate runs the IFC cases; --hosts ifc bonsai adds parity.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sync-root',type=Path,default=ROOT.parent/'usdaeco-sync')
    parser.add_argument('--pipe-root',type=Path,default=ROOT.parent/'usdaeco-pipe')
    parser.add_argument('--hosts',nargs='+',choices=['ifc','bonsai'],default=['ifc'])
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    if not (args.sync_root / 'scenarios/run.py').is_file():
        parser.exit(2, 'NOT RUN: the selected sync release has no legacy scenario runner; use the owning integration round-trip example.\n')
    kit=Path(os.environ.get('TOOLCHAIN_DIR',ROOT.parent/'usdaeco-toolchain'))
    buildup=Path(os.environ.get('AECO_BUILDUP_ROOT',ROOT.parent/'usdaeco-buildup'))
    core=Path(os.environ.get('AECO_CORE_ROOT',ROOT.parent/'usdaeco-core'))
    sys.path[:0]=[str(ROOT/'tools'),str(kit/'tools'),str(args.sync_root),str(args.pipe_root/'tools'),str(buildup/'tools')]
    from pluginset import plugin_set
    from usdaeco_wall import plugin_paths
    with tempfile.TemporaryDirectory(prefix='wall-sync-') as temporary:
        tmp=Path(temporary)
        aggregate=tmp/'plugins'
        pipe = args.pipe_root/'usdAecoPipe'
        if not (pipe/'plugInfo.json').is_file():
            pipe = args.pipe_root/'plugins/usdAecoPipe/resources'
        plugin_set(aggregate,[ROOT/'usdAecoWall',pipe],plugin_paths()[:3])
        os.environ['AECO_KIND_PLUGIN']=str(aggregate)
        os.environ['AECO_CORE']=str(core)
        from scenarios.run import prepare, cli, author_case, assert_case
        from scenarios.compare import compare
        from aeco_sync.stack import Session
        from usdaeco_wall.importer import import_wall
        from usdaeco_wall.validators import validate_stage
        from usdaeco_wall import iter_walls
        from usdaeco_pipe.importer import import_pipe
        from pxr import Sdf
        cases=json.loads((args.sync_root/'scenarios/cases.json').read_text())
        report={'hosts':{host:[] for host in args.hosts},'parity':{}}
        for case in cases:
            if case['id'] not in ('W-joined','W-neighbour'):
                continue
            directory=tmp/case['id']
            prepare(directory)
            import_wall(directory/'model.usda',directory/'baseline.ifc',directory/'wall.usda')
            import_pipe(directory/'wall.usda',directory/'baseline.ifc',directory/'kinds.usda')
            sessions={}
            for host in args.hosts:
                if host not in case['hosts']:
                    continue
                session_dir=directory/host
                cli('init',directory/'kinds.usda',directory/'baseline.ifc','--directory',session_dir)
                session=Session(session_dir/'stage.usda')
                issues=validate_stage(session.current())
                assert not issues, [(e.GetName(),e.GetMessage()) for e in issues]
                author_case(session,case)
                result=cli('--stage',session.path,'apply','--host',host)
                entry=assert_case(session,case,result)
                issues=validate_stage(session.current())
                assert not issues, [(e.GetName(),e.GetMessage()) for e in issues]
                report['hosts'][host].append(entry)
                sessions[host]=session
                print('PASS',case['id'],host,'with real importers and wall/build-up validation',flush=True)
            if len(sessions)==2:
                # The adapters emit different receipt scopes: the IFC adapter
                # writes its touched closure, Bonsai also reports other model
                # elements. Compare resolved walls, including inherited facts,
                # rather than demanding identical sparsity in their layers.
                snapshots=[]
                for host,session in sessions.items():
                    current=session.current()
                    flat=current.Flatten()
                    snapshot=Sdf.Layer.CreateAnonymous('walls.usda')
                    for wall in iter_walls(current):
                        Sdf.CreatePrimInLayer(snapshot,wall.GetPath())
                        Sdf.CopySpec(flat,wall.GetPath(),snapshot,wall.GetPath())
                    path=directory/(host+'-walls.usda')
                    snapshot.Export(str(path)); snapshots.append(path)
                parity=compare(*snapshots)
                parity['scope']='resolved wall subtrees including inherited catalog values'
                assert not parity['differences'],parity
                report['parity'][case['id']]=parity
                print('PASS parity',case['id'],str(parity['equal'])+'/'+str(parity['compared']),flush=True)
        assert any(report['hosts'].values()),'No matching wall scenarios ran'
        if args.report:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
