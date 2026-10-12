"""OKX-only paper adapter; signals from the historically losing baseline, not promoted research."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from MultiAssetPaperStrategy import MultiAssetPaperStrategy


class OkxPaperStrategy(MultiAssetPaperStrategy):
    """Same signals and fixed risk policy, with an independently persisted OKX profile."""
