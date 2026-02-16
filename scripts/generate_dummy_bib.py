#!/usr/bin/env python3
"""
Generate a dummy .bib file with many entries and unique keys, for profiling
bibtexparser load time (e.g. ~11470 entries to match issue #86).
Usage:
  python scripts/generate_dummy_bib.py [--count 11470] [--out dummy.bib]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Minimal article template; keys will be unique
TEMPLATE = """@article{{{key},
  author = {{Author{idx} and Second Author{idx}}},
  title = {{Title of paper number {idx} with some text}},
  journal = {{Dummy Journal}},
  year = {{{year}}},
  volume = {{{vol}}},
  number = {{{idx}}},
  pages = {{1--10}},
  doi = {{10.1000/dummy.{idx}}},
}}
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Generate dummy bib with unique keys for load profiling")
    p.add_argument("--count", type=int, default=11470, help="Number of entries (default: 11470)")
    p.add_argument("--out", type=str, default="dummy_library.bib", help="Output .bib path")
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = args.count

    with open(out, "w") as f:
        for i in range(1, n + 1):
            # Unique key: avoid special chars, keep readable
            key = f"Author{i}_Year{1900 + (i % 125)}_Dummy{i}"
            year = 1900 + (i % 125)
            vol = (i % 50) + 1
            f.write(TEMPLATE.format(key=key, idx=i, year=year, vol=vol))

    print(f"Wrote {n} entries to {out}", file=sys.stderr)
    print(str(out))


if __name__ == "__main__":
    main()
