"""`python -m papers`. The `papers` and `papers-cli` commands also call
main_clean_exit from here (see [project.scripts] in pyproject.toml)."""
from papers.cli import main_clean_exit

if __name__ == "__main__":
    main_clean_exit()
