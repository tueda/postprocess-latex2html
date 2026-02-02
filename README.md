# postprocess-latex2html

This script post-processes
[LaTeX2HTML](https://github.com/latex2html/latex2html)-generated files.

## Install

Either download the [script](https://raw.githubusercontent.com/tueda/postprocess-latex2html/refs/heads/main/postprocess-latex2html.py)
or install it with:
```bash
pip install git+https://github.com/tueda/postprocess-latex2html.git
```

## Usage

If you downloaded the script, run:
```bash
python3 postprocess-latex2html.py *.html *.css
```

If you installed it with `pip`, run:
```bash
postprocess-latex2html *.html *.css
```

## Development

```bash
# setup
uv sync
uv run pre-commit install

# linting and formatting
uv run pre-commit run --all-files

# tests
uv run pytest

# parallel tests
uv run pytest -n auto

# coverage
uv run pytest --cov=postprocess-latex2html
```

## License

MIT
