# postprocess-latex2html

This [script](#file-postprocess-latex2html-py) post-processes
[LaTeX2HTML](https://github.com/latex2html/latex2html)-generated files.

## Install

Either download the [script](https://gist.githubusercontent.com/tueda/cb625f9711d026c0fe4989b9f13f0a26/raw/postprocess-latex2html.py)
or install it with:
```bash
pip install git+https://gist.github.com/tueda/cb625f9711d026c0fe4989b9f13f0a26.git
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
