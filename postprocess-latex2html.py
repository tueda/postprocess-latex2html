# !/bin/sh
""":" .

exec python3 "$0" "$@"
"""

__doc__ = """Post-process LateX2HTML output files."""

import argparse
import functools
import logging
import re
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal, overload


def _get_logger() -> logging.Logger:
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        logger.addHandler(handler)
    return logger


logger = _get_logger()


def remove_section_numbering(string: str) -> str:
    """Remove leading section numbering from a heading string.

    Examples
    --------
    >>> remove_section_numbering("1. Introduction")
    'Introduction'

    >>> remove_section_numbering("2.1.1 Theoretical Framework")
    'Theoretical Framework'

    """
    return re.sub(r"^\s*\d+(?:\.\d+)*\.?\s+", "", string)


DEFAULT_SECTION_SEPARATOR = " -- "


def slugify(string: str, sep: str = DEFAULT_SECTION_SEPARATOR) -> str:
    """Convert a string to a slug.

    Examples
    --------
    >>> slugify("Introduction to AdS/CFT")
    'introduction-to-ads_cft'

    >>> slugify("The preprocessor -- The preprocessor variables")
    'preprocessor-variables'

    >>> slugify("Output optimization -- Optimization options")
    'output-optimization-options'

    """

    def normalize(s: str) -> str:
        s = s.strip()
        s = s.rstrip("!?.")
        s = s.replace("$", " dollar ")
        s = s.replace("+", " plus ")
        s = re.sub(r"\[\s*\]", "_", s)
        s = re.sub(r"[^\w\s_-]", "_", s)
        s = re.sub(r"\s+", "-", s)
        s = re.sub(r"_+-", "-", s)
        s = re.sub(r"-_+", "-", s)
        s = re.sub(r"--+", "-", s)
        s = re.sub(r"__+", "_", s)
        return s.strip("-")

    def remove_leading_article(s: str) -> str:
        return re.sub(r"^(?:a|an|the)\b", "", s)

    def merge(s1: str, s2: str) -> str:
        if re.match(re.escape(s2) + r"\b", s1):
            return s1
        if re.match(re.escape(s1) + r"\b", s2):
            return s2
        for i in range(min(len(s1), len(s2)), 0, -1):
            ss1 = s1[-i:]
            if re.match(re.escape(ss1) + r"\b", s2):
                ss2 = s2[:i]
                if re.search(r"\b" + re.escape(ss2) + r"$", s1):
                    return s1 + s2[i:]
        return s1 + "-" + s2

    return normalize(
        functools.reduce(
            merge,
            (
                normalize(remove_leading_article(normalize(s)))
                for s in string.lower().split(sep)
            ),
        )
    )


def replace_n(string: str, old: str, new: str, counter: int = 0) -> tuple[str, int]:
    """Like `str.replace(old, new)`, but also return the replacement count."""
    n = string.count(old)
    if n > 0:
        string = string.replace(old, new)
    return string, counter + n


def plural_s(n: int) -> str:
    """Return `"s"` if `n` is not 1."""
    return "s" if n != 1 else ""


@dataclass(frozen=True, slots=True)
class Options:
    """Program options."""

    require_author: bool = False
    require_toc: bool = False
    section_sep: str = DEFAULT_SECTION_SEPARATOR


class StylesheetHrefCollector(HTMLParser):
    """Collector for the (single) stylesheet link element."""

    def __init__(self) -> None:  # noqa: D107  # overridden
        super().__init__()
        self.href: str | None = None
        self.count = 0

    def handle_starttag(  # noqa: D102  # overridden
        self, tag: str, attrs: Sequence[tuple[str, str | None]]
    ) -> None:
        if tag != "link":
            return
        a = dict(attrs)
        if (a.get("rel") or "").lower() != "stylesheet":
            return
        href = a.get("href")
        if href:
            self.href = href
            self.count += 1

    @overload
    @staticmethod
    def parse(text: str, *, strict: Literal[True]) -> str: ...

    @overload
    @staticmethod
    def parse(text: str, *, strict: Literal[False]) -> str | None: ...

    @staticmethod
    def parse(text: str, *, strict: bool = False) -> str | None:
        """Return the href attribute of the stylesheet link."""
        p = StylesheetHrefCollector()
        p.feed(text)
        if strict and p.count != 1:
            msg = f"Expected exactly one stylesheet link, but found {p.count}"
            raise RuntimeError(msg)
        return p.href


class TocCollector(HTMLParser):
    """Collector for the table of contents."""

    def __init__(self, section_separator: str = DEFAULT_SECTION_SEPARATOR) -> None:  # noqa: D107  # overridden
        super().__init__()
        self.section_separator = section_separator
        self.toc_found = False
        self.toc_ended = False
        self.in_toc = False
        self.current_href: str | None = None
        self.last_text: str | None = None
        self.text_buf: list[str] = []
        self.results: list[tuple[str, str]] = []
        self.list_stack: list[str] = []

    def handle_starttag(  # noqa: D102  # overridden
        self, tag: str, attrs: Sequence[tuple[str, str | None]]
    ) -> None:
        if not self.in_toc:
            return
        match tag:
            case "a":
                a = dict(attrs)
                if "href" not in a:
                    return
                href = a["href"]
                if href:
                    self.current_href = href
                    self.text_buf = []
            case "ul":
                self.list_stack.append(self.last_text or "")

    def handle_data(self, data: str) -> None:  # noqa: D102  # overridden
        if self.current_href:
            self.text_buf.append(data)

    def handle_endtag(self, tag: str) -> None:  # noqa: D102  # overridden
        if not self.in_toc:
            return
        match tag:
            case "a":
                if not self.current_href:
                    return
                text = "".join(self.text_buf).strip()
                text = remove_section_numbering(text)
                self.results.append(
                    (
                        self.current_href,
                        self.section_separator.join(
                            [s for s in self.list_stack if s] + [text]
                        ),
                    )
                )
                self.last_text = text
                self.current_href = None
                self.text_buf = []
            case "ul":
                self.list_stack.pop()

    def handle_comment(self, data: str) -> None:  # noqa: D102  # overridden
        s = data.strip().lower()
        if s == "table of contents":
            self.toc_found = True
            self.in_toc = True
        elif s == "end of table of contents":
            self.toc_ended = True
            self.in_toc = False

    @staticmethod
    def parse(
        text: str,
        *,
        section_separator: str = DEFAULT_SECTION_SEPARATOR,
        strict: bool = False,
    ) -> list[tuple[str, str]]:
        """Return the table of contents as a list of tuples (href, title)."""
        p = TocCollector(section_separator=section_separator)
        p.feed(text)
        if strict:
            if not p.toc_found:
                msg = "Table of contents not found"
                raise RuntimeError(msg)
            if not p.toc_ended:
                msg = "End of table of contents not found"
                raise RuntimeError(msg)
        return p.results


def process_html(path: Path, options: Options) -> None:
    """Process an HTML file."""
    t0 = time.perf_counter()
    logger.info("Processing: %s", path)

    text = path.read_text()
    old_text = text

    # Replace HREF="main.html#..." with HREF="#...".

    text = _fix_href(text)

    # Generate permalinks for the table of contents.

    text = _fix_toc(text, options)

    # Repair malformed numeric character references (combining accents),
    # fixed upstream in v2025.
    # See: https://github.com/latex2html/latex2html/commit/b77ee98

    text = _fix_accents(text)

    # Remove STRONG markup for author. Fixed upstream as of February 2026.
    # See: https://github.com/latex2html/latex2html/commit/318864e

    text = _fix_author(text, options)

    # Save the changes if any.

    if text != old_text:
        path.write_text(text)
    else:
        logger.info("  No changes made")
    elapsed = time.perf_counter() - t0
    logger.info("  Finished in %.3f s", elapsed)


def _fix_href(text: str) -> str:
    css = StylesheetHrefCollector.parse(text, strict=True)
    main_html = Path(css).with_suffix(".html")

    text, n = replace_n(text, f'HREF="{main_html.name}#', 'HREF="#')
    if n > 0:
        logger.info("  Fixed %d link URL%s", n, plural_s(n))

    return text


def _fix_toc(text: str, options: Options) -> str:
    toc = TocCollector.parse(
        text,
        section_separator=options.section_sep,
        strict=options.require_toc,
    )

    if not toc:
        return text

    old_text = text
    slugs = _make_slugs(toc, options)

    i = 0

    def repl_href(m: re.Match[str]) -> str:
        nonlocal i

        s = m.group(0)

        if i >= len(toc):
            return s

        link = toc[i][0]
        if s == link:
            s = f"#SECTION-{slugs[i]}"
            i += 1

        return s

    text = re.sub(
        r'(?<=HREF=")[^"]+(?=")', repl_href, text, flags=re.IGNORECASE | re.DOTALL
    )

    j = 0

    def repl_id(m: re.Match[str]) -> str:
        nonlocal j

        s = m.group(0)

        if j >= len(toc):
            return s

        anchor = toc[j][0][1:]
        if s == anchor:
            s = f"SECTION-{slugs[j]}"
            j += 1

        return s

    text = re.sub(
        r'(?<=ID=")[^"]+(?=")', repl_id, text, flags=re.IGNORECASE | re.DOTALL
    )

    if i != len(toc) or j != len(toc):
        msg = "Mismatch in number of TOC entries processed"
        raise RuntimeError(msg)

    if text != old_text:
        logger.info("  Generated %d permalink%s", i, plural_s(i))

    return text


def _make_slugs(toc: list[tuple[str, str]], options: Options) -> list[str]:
    seen: dict[str, str] = {}
    slugs = []

    for href, title in toc:
        if not href.startswith("#SECTION"):
            continue
        slug = slugify(title, sep=options.section_sep)
        if slug in seen:
            i = 2
            while True:
                if slug[-1] == "_" or slug[-1] == "-":
                    new_slug = f"{slug}{i}"
                else:
                    new_slug = f"{slug}-{i}"
                if new_slug not in seen:
                    break
                i += 1
            logger.info("  Two titles ended up with the same slug: %s", slug)
            logger.info("    first:  %s", seen[slug])
            logger.info("    second: %s", title)
            logger.info("  The slug for the second has been changed: %s", new_slug)
            slug = new_slug
        else:
            seen[slug] = title
        slugs.append(slug)
    return slugs


def _fix_accents(text: str) -> str:
    n = 0
    text, n = replace_n(text, "&&#x300;#305;", "&igrave;", n)  # \`{\i}
    text, n = replace_n(text, "&&#x301;#305;", "&iacute;", n)  # \'{\i}
    text, n = replace_n(text, "&&#x308;#305;", "&iuml;", n)  # \"{\i}

    if n > 0:
        logger.info(
            "  Fixed %d malformed numeric character reference%s", n, plural_s(n)
        )

    return text


def _fix_author(text: str, options: Options) -> str:
    count = 0
    n = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count, n

        s = m.group(0)
        s, n1 = replace_n(s, "<STRONG>", "")
        s, n2 = replace_n(s, "</STRONG>", "")

        if n1 != n2:
            msg = "Mismatched STRONG tags in author list"
            raise RuntimeError(msg)

        count += 1

        if n1 > 0:
            n += 1

        return s

    text = re.sub(
        r'<DIV\s+CLASS="author_info">\s*.*?\s*</DIV>', repl, text, flags=re.DOTALL
    )

    if options.require_author and count == 0:
        msg = "Author list not found"
        raise RuntimeError(msg)

    if count > 1:
        msg = f"Expected exactly one author list, but found {count}"
        raise RuntimeError(msg)

    if n > 0:
        logger.info("  Fixed %d markup in author list%s", n, plural_s(n))

    return text


def process_css(path: Path) -> None:
    """Process a CSS file."""
    t0 = time.perf_counter()
    logger.info("Processing: %s", path)

    text = path.read_text()
    old_text = text

    # Nothing for now.

    # Save the changes if any.

    if text != old_text:
        path.write_text(text)
    else:
        logger.info("  No changes made")
    elapsed = time.perf_counter() - t0
    logger.info("  Finished in %.3f s", elapsed)


def process_files(files: Sequence[Path], options: Options) -> None:
    """Process input files based on their file extension."""
    for f in files:
        path = Path(f)
        suffix = path.suffix.lower()
        match suffix:
            case ".html" | ".htm":
                process_html(path, options)
            case ".css":
                process_css(path)
            case _:
                msg = f"Unsupported file type: {suffix} ({path})"
                raise RuntimeError(msg)


def main(args: Sequence[str] | None = None) -> None:
    """Entry point."""
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(usage="%(prog)s [options] file...")
    parser.add_argument("file", nargs="+", help=argparse.SUPPRESS)
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable verbose output"
    )
    parser.add_argument(
        "--has-author", action="store_true", help="document has author list"
    )
    parser.add_argument(
        "--has-toc", action="store_true", help="document has table of contents"
    )
    parsed_args = parser.parse_args(args)

    if parsed_args.verbose:
        logger.setLevel(logging.DEBUG)

    process_files(
        [Path(f) for f in parsed_args.file],
        Options(require_author=parsed_args.has_author, require_toc=parsed_args.has_toc),
    )


if __name__ == "__main__":
    main()
