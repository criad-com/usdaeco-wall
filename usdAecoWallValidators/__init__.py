"""Load the six wall rules through the native Python validator plugin path."""
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(Path(os.environ.get("TOOLCHAIN_DIR", ROOT.parent / "usdaeco-toolchain")) / "tools")]
from usdaeco_wall import validators as legacy
from usdaeco_check.validation import register_prim_validator, register_stage_validator, wrap_legacy
from . import validatorTokens as tokens

register_prim_validator(tokens.WALLKINDMISMATCH_CHECKER,
    wrap_legacy(tokens.WALLKINDMISMATCH_CHECKER, lambda target: legacy._kind(target, None)), ["UsdAecoWallWallAPI"])
register_prim_validator(tokens.WALLMISSINGAXIS_CHECKER,
    wrap_legacy(tokens.WALLMISSINGAXIS_CHECKER, lambda target: legacy._axis(target, None)), ["UsdAecoWallWallAPI"])
register_prim_validator(tokens.WALLJOINASYMMETRIC_CHECKER,
    wrap_legacy(tokens.WALLJOINASYMMETRIC_CHECKER, lambda target: legacy._joins(target, None)), ["UsdAecoWallWallAPI"])
register_stage_validator(tokens.WALLJOINEDENDEXTENDED_CHECKER,
    wrap_legacy(tokens.WALLJOINEDENDEXTENDED_CHECKER, lambda target: legacy._extended(target, None)))
register_stage_validator(tokens.WALLOPENINGOUTSIDEHOST_CHECKER,
    wrap_legacy(tokens.WALLOPENINGOUTSIDEHOST_CHECKER, lambda target: legacy._openings(target, None)))
register_prim_validator(tokens.WALLSIZEMISMATCH_CHECKER,
    wrap_legacy(tokens.WALLSIZEMISMATCH_CHECKER, lambda target: legacy._size(target, None)), ["UsdAecoWallWallAPI"])
