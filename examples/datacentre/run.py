#!/usr/bin/env python3
"""Compose the pinned clash stage, promote walls, derive L01 axes and render."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
KIT = Path(os.environ.get('TOOLCHAIN_DIR', ROOT.parent / 'usdaeco-toolchain'))
sys.path[:0] = [str(ROOT / 'tools'), str(KIT / 'tools')]
from usdaeco_wall import register_plugins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    os.environ.setdefault('AECO_DATACENTRE_ROOT', str(ROOT.parent / 'usdaeco-datacentre'))
    register_plugins()
    from usdaeco_wall.example import hook
    from usdaeco_check.example import run_example
    from usdaeco_render import render
    example = Path(__file__).resolve().parent
    # The shared harness refreshes ignored inputs/source from AECO_DATACENTRE_ROOT.
    manifest = run_example(example, hook, variant='clash', keywords=[], publish=args.publish)
    # Retain the guide-inclusive review beside the stock USD result proof.
    print('== stage: render corner with guide,proxy,render', flush=True)
    manifest['renders'] = render(example / 'out/example.usda', output=example / 'out/renders', purposes='guide,proxy,render')
    manifest['render_purposes'] = ['guide', 'proxy', 'render']
    manifest['review'] = {'extent_guides': 'excluded', 'camera': 'framed from composed corner bounds'}
    (example / 'out/manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    if args.publish:
        (example / 'renders').mkdir(exist_ok=True)
        for record in manifest['renders']:
            shutil.copyfile(example / 'out' / record['path'], example / record['path'])
        shutil.copyfile(example / 'out/manifest.json', example / 'manifest.json')
        shutil.copyfile(example / 'renders/partition_corner.png', ROOT / 'usdAecoWall/userDoc/usdAecoWallExample.png')
    print(json.dumps({'source': manifest['source']['mode'], 'renders': len(manifest['renders'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
