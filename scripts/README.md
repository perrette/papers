# Scripts

## Dummy Bib and bibtexparser load benchmark

For profiling/benchmarking bibtexparser load time with a large library (e.g. [issue #86](https://github.com/perrette/papers/issues/86)).

### Generate dummy bib (~11k entries, unique keys)

```bash
python3 scripts/generate_dummy_bib.py --count 11470 --out dummy_library.bib
```

Output is written to `dummy_library.bib` (or `--out` path). Keys are unique (e.g. `Author1_Year1990_Dummy1`, …).

### Benchmark load time: v1 vs v2

- **v1 (current dependency)**: use project venv  
  ```bash
  .venv/bin/python3 scripts/benchmark_bibtexparser_load.py dummy_library.bib
  ```
- **v2**: use a separate venv with pre-release bibtexparser  
  ```bash
  python3 -m venv .venv-bib2
  .venv-bib2/bin/pip install --pre bibtexparser
  .venv-bib2/bin/python3 scripts/benchmark_bibtexparser_load.py dummy_library.bib
  ```

Compare the “mean” time for v1 `loads` vs v2 `parse_string` on the same file. Example (11 470 entries, ~3 MB): v1 ~17 s, v2 ~0.4 s (large speedup with v2).

### papers add: how many times is the library parsed?

The **main bibtex file is parsed only once** in the `papers add` pipeline:

1. `addcmd()` calls `get_biblio(config)` → `Biblio.load(config.bibtex, ...)` which does `open(bibtex).read()` then `bibtexparser.loads(bibtexs)` **once**.
2. For each PDF, `add_pdf()` calls `bibtexparser.loads(bibtex)` on the **small** string returned by `extract_pdf_metadata()` (a single entry), not on the full library.
3. For each `.bib` file, `add_bibtex_file()` parses only that file’s content.

So the slowness with a 11k-entry library is from that single initial `Biblio.load()`. Using bibtexparser v2 (when available) for that single parse would reduce add latency for large libraries.
