#!/usr/bin/env python3
"""
Benchmark bibtexparser load time for a large .bib (e.g. ~11k entries).
Compares v1 (loads) with v2 (parse_string) when both are available.
Usage:
  python scripts/benchmark_bibtexparser_load.py [dummy_library.bib]
  python scripts/benchmark_bibtexparser_load.py  # generates dummy if needed
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Default: same repo-level dummy bib
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_BIB = REPO_ROOT / "dummy_library.bib"


def ensure_dummy_bib(path: Path, count: int = 11470) -> Path:
    if path.exists():
        return path
    gen = SCRIPT_DIR / "generate_dummy_bib.py"
    if not gen.exists():
        raise SystemExit(f"Bib not found: {path}. Run: python scripts/generate_dummy_bib.py --out {path}")
    import subprocess
    subprocess.run([sys.executable, str(gen), "--count", str(count), "--out", str(path)], check=True)
    return path


def benchmark_v1(content: str, rounds: int = 3) -> list[float]:
    import bibtexparser
    times = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        db = bibtexparser.loads(content)
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        assert hasattr(db, "entries")
        n = len(db.entries)
    return times


def benchmark_v2(content: str, rounds: int = 3) -> list[float] | None:
    try:
        import bibtexparser
        if not hasattr(bibtexparser, "parse_string"):
            return None
    except ImportError:
        return None
    times = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        lib = bibtexparser.parse_string(content)
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        n = len(lib.entries) if hasattr(lib, "entries") else len(lib)
    return times


def main() -> None:
    bib_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BIB
    bib_path = ensure_dummy_bib(bib_path)
    content = bib_path.read_text()
    n_entries = content.count("@article{") + content.count("@inproceedings{") + content.count("@book{")
    if not n_entries:
        n_entries = content.count("\n@") or content.count("@")
    print(f"Bib: {bib_path}, size: {len(content)/1024/1024:.2f} MB, ~{n_entries} entries", flush=True)

    # V1 (loads) - when run with project venv (bibtexparser < 2)
    try:
        import bibtexparser
        v1_version = getattr(bibtexparser, "__version__", "?")
        has_loads = hasattr(bibtexparser, "loads")
    except ImportError:
        v1_version = "not installed"
        has_loads = False
    v1_times = None
    if has_loads:
        print(f"\nbibtexparser (v1 API): version {v1_version}", flush=True)
        v1_times = benchmark_v1(content)
        for i, t in enumerate(v1_times):
            print(f"  round {i+1}: {t:.3f}s", flush=True)
        print(f"  mean: {sum(v1_times)/len(v1_times):.3f}s", flush=True)
    else:
        print(f"\nbibtexparser (v1 API): not available in this env (no loads)", flush=True)

    # V2 (parse_string) - when run with e.g. .venv-bib2 (pip install --pre bibtexparser)
    try:
        import bibtexparser as bp2
        has_parse_string = hasattr(bp2, "parse_string")
    except ImportError:
        has_parse_string = False
    if has_parse_string:
        print(f"\nbibtexparser (v2 API): parse_string", flush=True)
        v2_times = benchmark_v2(content)
        if v2_times:
            for i, t in enumerate(v2_times):
                print(f"  round {i+1}: {t:.3f}s", flush=True)
            v2_mean = sum(v2_times) / len(v2_times)
            print(f"  mean: {v2_mean:.3f}s", flush=True)
            if v1_times and len(v1_times) > 0:
                v1_mean = sum(v1_times) / len(v1_times)
                ratio = v2_mean / v1_mean
                print(f"  v2/v1: {ratio:.2f}x", flush=True)
    else:
        print("\nbibtexparser v2 (parse_string) not available; use a venv with: pip install --pre bibtexparser", flush=True)


if __name__ == "__main__":
    main()
