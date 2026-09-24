#!/usr/bin/env python3
"""Create the small output tree for the full-production refine5 replay."""

from pathlib import Path
import sys


SETS = ("b1", "b2", "c2", "c3", "d1", "e1", "e2", "e3", "f1", "f2", "g1", "g2")


def main() -> None:
    root = Path(sys.argv[1])
    for code in SETS:
        (root / code / "refine5").mkdir(parents=True, exist_ok=True)
        (root / code / "plots" / "refine5").mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    main()
