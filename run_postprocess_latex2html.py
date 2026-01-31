"""Console entry point."""

import runpy
from pathlib import Path


def main() -> None:
    """Execute the main script."""
    path = Path(__file__).with_name("postprocess-latex2html.py")
    runpy.run_path(str(path), run_name="__main__")
