#!/usr/bin/env python3
"""Build small, independently replaceable contribution-graph paint batches.

Each visible glyph is its own Git history, rooted at the repository's fixed
cleanup commit.  The histories are merged into ``main`` by the workflow.  A
monthly refresh can therefore replace one glyph per day without rewriting the
other glyphs.

The default design uses twenty commits per lit cell.  On this account's clean
2024 and 2025 calendars ten was the first count rendered at GitHub's darkest
contribution level, so twenty leaves useful margin for normal activity.

Usage:
    python art/paint.py --preview
    python art/paint.py --list-components --order repaint
    python art/paint.py --stream --component 00-h \
        --root <sha> --head-tree <sha> --branch paint-rebuild \
        --name "Jane Doe" --email jane@example.com
"""

import argparse
import hashlib
import sys
from dataclasses import dataclass
from datetime import date, timedelta


# Five-row glyphs, drawn on rows 1..5 of the seven-row graph. ``X`` is lit.
FONT = {
    "H": ["X..X", "X..X", "XXXX", "X..X", "X..X"],
    "I": ["X", "X", "X", "X", "X"],
    " ": ["..", "..", "..", "..", ".."],
    "F": ["XXX", "X..", "XX.", "X..", "X.."],
    "O": [".XX.", "X..X", "X..X", "X..X", ".XX."],
    "L": ["X.", "X.", "X.", "X.", "XX"],
    "K": ["X..X", "X.X.", "XX..", "X.X.", "X..X"],
    "S": [".XXX", "X...", ".XX.", "...X", "XXX."],
    "!": ["X", "X", "X", ".", "X"],
}

WEEKS = 53
DEFAULT_MESSAGE = "HI FOLKS!"
DEFAULT_COMMITS_PER_PIXEL = 20
DEFAULT_MAX_COMPONENT_COMMITS = 350  # allows modest glyph edits; default max 241
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
PAINTER_FORMAT_VERSION = 1


@dataclass(frozen=True)
class Component:
    """One independently replaceable glyph in graph coordinates."""

    slug: str
    label: str
    pixels: frozenset


@dataclass(frozen=True)
class PlacedComponent:
    """One component mapped from graph coordinates to calendar dates."""

    slug: str
    label: str
    cells: dict


def positive_int(value):
    """Argparse type for values that must be greater than zero."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _slug_for(label, index):
    names = {"!": "bang"}
    name = names.get(label, label.lower() if label.isalnum() else "glyph")
    return f"{index:02d}-{name}"


def build_components(message):
    """Return (components, art_width) with absolute graph coordinates."""
    unsupported = sorted(set(message) - set(FONT))
    if unsupported:
        rendered = ", ".join(repr(ch) for ch in unsupported)
        raise ValueError(f"unsupported message character(s): {rendered}")

    components = []
    col = 0
    component_index = 0
    for ch in message:
        glyph = FONT[ch]
        pixels = {
            (col + c, r + 1)
            for r, line in enumerate(glyph)
            for c, cell in enumerate(line)
            if cell == "X"
        }
        if pixels:
            components.append(
                Component(
                    _slug_for(ch, component_index),
                    ch,
                    frozenset(pixels),
                )
            )
            component_index += 1
        col += len(glyph[0]) + 1

    if not components:
        raise ValueError("message must contain at least one lit glyph")
    return components, col - 1  # omit the final inter-glyph spacer


def build_pixels(message):
    """Return ({(col, row), ...}, art_width) for the message."""
    components, width = build_components(message)
    pixels = set().union(*(component.pixels for component in components))
    return pixels, width


def layout_components(message, end_date):
    """Map every component to dates in a centered contribution-calendar grid."""
    components, width = build_components(message)
    if width > WEEKS:
        raise ValueError(
            f"art is {width} columns wide; the graph only has {WEEKS}"
        )

    # Column 52 is the week containing end_date; weeks start on Sunday.
    end_sunday = end_date - timedelta(days=(end_date.weekday() + 1) % 7)
    col0_sunday = end_sunday - timedelta(weeks=WEEKS - 1)
    start_col = (WEEKS - width) // 2
    placed = []
    for component in components:
        cells = {
            col0_sunday + timedelta(days=7 * (start_col + col) + row):
            (start_col + col, row)
            for col, row in component.pixels
        }
        placed.append(PlacedComponent(component.slug, component.label, cells))
    return placed, width, start_col


def layout(message, end_date):
    """Compatibility helper returning all dated cells as a single mapping."""
    components, width, start_col = layout_components(message, end_date)
    cells = {}
    for component in components:
        cells.update(component.cells)
    return cells, width, start_col


def component_plan(
    message,
    end_date,
    component_slug,
    commits_per_pixel,
    max_component_commits,
):
    """Return one placed component after enforcing the per-batch limit."""
    components, width, start_col = layout_components(message, end_date)
    matches = [component for component in components
               if component.slug == component_slug]
    if not matches:
        available = ", ".join(component.slug for component in components)
        raise ValueError(
            f"unknown component {component_slug!r}; choose one of: {available}"
        )
    component = matches[0]
    generated = len(component.cells) * commits_per_pixel + 1
    if generated > max_component_commits:
        safe_strokes = max(
            0, (max_component_commits - 1) // len(component.cells)
        )
        raise ValueError(
            f"component {component.slug} would generate {generated:,} commits, "
            f"exceeding the {max_component_commits:,}-commit batch limit; use "
            f"at most --commits-per-pixel {safe_strokes}"
        )
    return component, width, start_col, generated


def repaint_slugs(message):
    """Return component slugs newest/rightmost first for gap-safe repainting."""
    components, _ = build_components(message)
    return [component.slug for component in reversed(components)]


def component_token(message, component_slug, end_date, commits_per_pixel):
    """Return a stable token that changes when a component's drawing changes."""
    components, width, start_col = layout_components(message, end_date)
    matches = [component for component in components
               if component.slug == component_slug]
    if not matches:
        available = ", ".join(component.slug for component in components)
        raise ValueError(
            f"unknown component {component_slug!r}; choose one of: {available}"
        )
    component = matches[0]
    payload = repr((
        PAINTER_FORMAT_VERSION,
        width,
        start_col,
        component.slug,
        sorted((day.isoformat(), position)
               for day, position in component.cells.items()),
        commits_per_pixel,
    )).encode()
    return hashlib.sha256(payload).hexdigest()[:12]


def component_marker(message, component_slug, end_date, commits_per_pixel):
    """Return the component-tip subject used as persistent workflow state."""
    token = component_token(
        message,
        component_slug,
        end_date,
        commits_per_pixel,
    )
    return f"repaint: {component_slug} {end_date} {token}"


def preview(message, end_date, commits_per_pixel, max_component_commits):
    components, width, start_col = layout_components(message, end_date)
    lit = {
        position
        for component in components
        for position in component.cells.values()
    }
    print(
        f"graph window ends {end_date}; art {width} cols wide, "
        f"starting at column {start_col}"
    )
    for row in range(7):
        print("".join(
            "#" if (col, row) in lit else "." for col in range(WEEKS)
        ))

    generated = [
        len(component.cells) * commits_per_pixel + 1
        for component in components
    ]
    largest = max(generated)
    if largest > max_component_commits:
        raise ValueError(
            f"largest component would generate {largest:,} commits, exceeding "
            f"the {max_component_commits:,}-commit batch limit"
        )
    cells = [day for component in components for day in component.cells]
    total_paint = sum(len(component.cells) for component in components)
    generated_above_root = sum(generated) + 1  # plus the main join commit
    print(
        f"{total_paint} pixels, {commits_per_pixel} commits each; "
        f"{generated_above_root} generated commits above the fixed root, "
        f"largest component batch {largest} (limit {max_component_commits}); "
        f"dates {min(cells)} .. {max(cells)}"
    )


def emit_stream(out, args):
    """Emit a fast-import stream for exactly one component branch."""
    component, _, _, _ = component_plan(
        args.message,
        args.end_date,
        args.component,
        args.commits_per_pixel,
        args.max_commits,
    )
    for label, value in (
        ("name", args.name),
        ("email", args.email),
        ("branch", args.branch),
        ("root", args.root),
        ("head tree", args.head_tree),
    ):
        if "\n" in value or "\r" in value:
            raise ValueError(f"{label} cannot contain a newline")

    painter_ident = f"{args.name} <{args.email}>"
    bot_ident = f"{BOT_NAME} <{BOT_EMAIL}>"
    ref = f"refs/heads/{args.branch}"
    total = len(component.cells) * args.commits_per_pixel
    out.write(b"feature done\n")

    def commit(message, timestamp, ident, body=None, first=False, restore=False):
        out.write(f"commit {ref}\n".encode())
        out.write(f"author {ident} {timestamp} +0000\n".encode())
        out.write(f"committer {ident} {timestamp} +0000\n".encode())
        payload = message.encode()
        out.write(b"data %d\n%s\n" % (len(payload), payload))
        if first:
            out.write(f"from {args.root}\n".encode())
        if restore:
            out.write(f"M 040000 {args.head_tree} \x22\x22\n".encode())
        elif body is not None:
            blob = body.encode()
            out.write(b"M 100644 inline art/.paint-stroke\n")
            out.write(b"data %d\n%s\n" % (len(blob), blob))
        out.write(b"\n")

    first = True
    done = 0
    for day in sorted(component.cells):
        col, row = component.cells[day]
        epoch_day = (day - date(1970, 1, 1)).days * 86400
        for stroke in range(args.commits_per_pixel):
            done += 1
            commit(
                f"paint {component.slug} {day} cell({col},{row}) "
                f"[{done}/{total}]",
                epoch_day + 12 * 3600 + stroke,
                painter_ident,
                body=(
                    f"{component.slug} {day} cell({col},{row}) "
                    f"stroke {stroke + 1}\n"
                ),
                first=first,
            )
            first = False

    # The tip has the fixed root tree and bot identity, so it neither leaves a
    # scratch file in the repository nor adds an off-design user contribution.
    tip_timestamp = (
        (args.end_date - date(1970, 1, 1)).days * 86400 + 13 * 3600
    )
    commit(
        component_marker(
            args.message,
            component.slug,
            args.end_date,
            args.commits_per_pixel,
        ),
        tip_timestamp,
        bot_ident,
        restore=True,
    )
    out.write(b"done\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=date.today(),
        help="pinned graph-window date for this monthly cycle",
    )
    parser.add_argument(
        "--commits-per-pixel",
        type=positive_int,
        default=DEFAULT_COMMITS_PER_PIXEL,
        help="commits per lit cell (default: %(default)s)",
    )
    parser.add_argument(
        "--max-commits",
        type=positive_int,
        default=DEFAULT_MAX_COMPONENT_COMMITS,
        help="maximum commits in one component branch (default: %(default)s)",
    )
    parser.add_argument("--preview", action="store_true", help="print the grid")
    parser.add_argument(
        "--list-components",
        action="store_true",
        help="print one component slug per line",
    )
    parser.add_argument(
        "--marker",
        action="store_true",
        help="print the expected tip subject for --component",
    )
    parser.add_argument(
        "--order",
        choices=("left", "repaint"),
        default="left",
        help="component order for --list-components",
    )
    parser.add_argument("--stream", action="store_true", help="emit fast-import")
    parser.add_argument("--component", help="component slug for --stream")
    parser.add_argument("--root", help="SHA of the fixed cleanup root")
    parser.add_argument("--head-tree", help="tree SHA restored at the branch tip")
    parser.add_argument("--name", help="paint commit author name")
    parser.add_argument("--email", help="paint commit author email")
    parser.add_argument("--branch", default="paint-rebuild")
    parser.add_argument("--output", help="write stream to a file (default stdout)")
    args = parser.parse_args()

    try:
        if args.stream:
            for required in ("component", "root", "head_tree", "name", "email"):
                if not getattr(args, required):
                    parser.error(
                        f"--stream requires --{required.replace('_', '-')}"
                    )
            if args.output:
                with open(args.output, "wb") as stream:
                    emit_stream(stream, args)
            else:
                emit_stream(sys.stdout.buffer, args)
        elif args.list_components:
            components, _ = build_components(args.message)
            slugs = [component.slug for component in components]
            if args.order == "repaint":
                slugs.reverse()
            print("\n".join(slugs))
        elif args.marker:
            if not args.component:
                parser.error("--marker requires --component")
            print(component_marker(
                args.message,
                args.component,
                args.end_date,
                args.commits_per_pixel,
            ))
        else:
            preview(
                args.message,
                args.end_date,
                args.commits_per_pixel,
                args.max_commits,
            )
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
