"""Wall promotion and validation without requiring a package install."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("import", help="promote SI wall properties from USD, optionally enriching from IFC")
    p.add_argument("stage", type=Path)
    p.add_argument("--ifc", type=Path)
    p.add_argument("-o", "--out", type=Path, required=True)
    p = commands.add_parser("check", help="run the six wall and build-up rules")
    p.add_argument("stage")
    p.add_argument("--profile", type=Path)
    p = commands.add_parser("validators", help="list registered wall rules")
    args = parser.parse_args(argv)
    from . import register_plugins
    register_plugins()
    from pxr import Usd, UsdValidation
    from . import validators
    try:
        if args.command == "import":
            if args.ifc:
                from .importer import import_wall
                result = import_wall(args.stage, args.ifc, args.out)
            else:
                from .stage_import import import_stage
                result = import_stage(args.stage, args.out)
        elif args.command == "validators":
            validators.register()
            result = sorted(m.name for m in UsdValidation.ValidationRegistry().GetValidatorMetadataForKeyword(validators.KEYWORD))
        else:
            stage = Usd.Stage.Open(args.stage)
            if not stage or stage.GetCompositionErrors():
                raise ValueError("Stage does not compose")
            issues = validators.validate_stage(stage, profile=args.profile)
            result = [{"name": e.GetName(), "severity": str(e.GetType()).split(".")[-1].lower(),
                       "paths": [str(site.GetPath()) for site in e.GetSites()], "message": e.GetMessage()} for e in issues]
            print(json.dumps(result, indent=2, sort_keys=True))
            return int(bool(validators.split(issues)[0]))
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, "aeco-wall: " + str(exc) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
