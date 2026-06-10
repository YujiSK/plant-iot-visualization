#!/usr/bin/env python3
"""Generate the Plant IoT wiring diagram from Graphviz DOT source."""

from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "wiring.dot"
OUTPUT = ROOT / "docs" / "wiring.svg"


def main() -> int:
    dot = shutil.which("dot")
    if dot is None:
        print(
            "Graphviz 'dot' was not found. Install it with: sudo apt install graphviz",
            file=sys.stderr,
        )
        return 1

    subprocess.run(
        [dot, "-Tsvg", str(SOURCE), "-o", str(OUTPUT)],
        check=True,
    )
    print(f"generated: {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
