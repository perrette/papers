# Configuration and install

## install: make bibtex and files directory persistent

```
$> papers install --bibtex papers.bib --filesdir files
papers configuration
* configuration file: /home/perrette/.config/papersconfig.json
* cache directory:    /home/perrette/.cache/papers
* absolute paths:     True
* files directory:    files (1 files, 5.8 MB)
* bibtex:            papers.bib (1 entries)
```

The configuration file is global (unless `--local` is specified), so from now
on, any `papers` command will know about these settings: no need to specify
bibtex file or files directory.

Running `papers install` again *updates* the existing configuration: options
you pass change, everything else is kept. Pass `--reset` to discard the
existing configuration and start over from defaults. Use `--no-prompt` to
accept all defaults non-interactively (at the prompts, `Enter` accepts the
proposed default, typing a value sets it, and `unset` clears it).

Type `papers status -v` to check your configuration.

You also notice a cache directory. All internet requests such as crossref
requests are saved in the cache directory. This happens regardless of whether
`papers` is installed or not.

## Local install

Sometimes it is desirable to have separate configurations. In that case a local
install is the way to go:

```
$> papers install --local
Bibtex file name [default to existing: papers.bib] [Enter/Yes/No]:
Files folder [default to new: papers] [Enter/Yes/No]: pdfs
papers configuration
* configuration file: papersconfig.json
* cache directory:    /home/perrette/.cache/papers
* absolute paths:     True
* git-tracked:        False
* files directory:    pdfs (90 files, 337.4 MB)
* bibtex:             papers.bib (82 entries)
```

Creates a local configuration file (`.papersconfig.json`) in the current
directory. By default, it expects existing or creates new `papers.bib`
bibliography and `files` folder in the local directory, though `papers` will
ask first unless explicitly provided. Note that every call from a subfolder
will also detect that configuration file (it has priority over global
install).

By default, the local install is meant to be portable with bibtex and files, so
the file paths are encoded relatively to the bibtex file. If instead absolute
paths make more sense (example use case: local bibtex file but central PDF
folder), then simply specify `--absolute-paths`:

```
papers install --local --absolute-paths --filesdir /path/to/central/pdfs
```

## Uninstall

Getting confused with papers config files scattered in subfolders? Check the
config with:

```
papers status -v
```

and remove the configuration file by hand (`rm ...`). Or use the `papers
uninstall` command:

```
papers uninstall
```

You may repeat `papers status -v` and cleaning until a satisfying state is
reached, or remove all config files recursively up to (and including) global
install:

```
papers uninstall --recursive
```

## Relative versus absolute paths

By default, the file paths in the bibtex are stored as absolute paths (starting
with `/`), except for local installs. It is possible to change this behaviour
explicitly during install or in a case-by-case basis with `--relative-paths` or
`--absolute-paths`, with or without install.
