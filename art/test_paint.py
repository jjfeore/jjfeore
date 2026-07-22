import argparse
import io
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

import paint


class PaintTests(unittest.TestCase):
    @staticmethod
    def git(repo, *args, input_bytes=None):
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            input=input_bytes,
            check=True,
            capture_output=True,
        ).stdout.decode().strip()

    def test_default_design_is_split_into_stable_components(self):
        components, width = paint.build_components(paint.DEFAULT_MESSAGE)

        self.assertEqual(width, 33)
        self.assertEqual(
            [component.slug for component in components],
            [
                "00-h",
                "01-i",
                "02-f",
                "03-o",
                "04-l",
                "05-k",
                "06-s",
                "07-bang",
            ],
        )
        self.assertEqual(
            [component.label for component in components],
            ["H", "I", "F", "O", "L", "K", "S", "!"],
        )
        self.assertEqual(
            [len(component.pixels) for component in components],
            [12, 5, 8, 10, 6, 10, 10, 4],
        )
        self.assertEqual(sum(len(component.pixels) for component in components), 65)

    def test_components_do_not_overlap(self):
        components, _ = paint.build_components(paint.DEFAULT_MESSAGE)
        all_pixels = [pixel for component in components for pixel in component.pixels]

        self.assertEqual(len(all_pixels), len(set(all_pixels)))

    def test_repaint_order_is_right_to_left(self):
        self.assertEqual(
            paint.repaint_slugs(paint.DEFAULT_MESSAGE),
            [
                "07-bang",
                "06-s",
                "05-k",
                "04-l",
                "03-o",
                "02-f",
                "01-i",
                "00-h",
            ],
        )

    def test_component_marker_tracks_date_design_and_intensity(self):
        marker = paint.component_marker(
            paint.DEFAULT_MESSAGE,
            "00-h",
            date(2026, 7, 1),
            paint.DEFAULT_COMMITS_PER_PIXEL,
        )

        self.assertRegex(
            marker,
            r"^repaint: 00-h 2026-07-01 [0-9a-f]{12}$",
        )
        self.assertNotEqual(
            marker,
            paint.component_marker(
                paint.DEFAULT_MESSAGE,
                "00-h",
                date(2026, 8, 1),
                paint.DEFAULT_COMMITS_PER_PIXEL,
            ),
        )
        self.assertNotEqual(
            marker,
            paint.component_marker(
                paint.DEFAULT_MESSAGE,
                "00-h",
                date(2026, 7, 1),
                paint.DEFAULT_COMMITS_PER_PIXEL + 1,
            ),
        )

    def test_default_history_and_rewrite_stay_below_guards(self):
        components, _, _ = paint.layout_components(
            paint.DEFAULT_MESSAGE, date(2026, 7, 1)
        )
        generated = [
            len(component.cells) * paint.DEFAULT_COMMITS_PER_PIXEL + 1
            for component in components
        ]

        # Above the fixed root: 1,300 paint commits, eight restores, one join.
        self.assertEqual(sum(generated) + 1, 1_309)
        self.assertEqual(max(generated), 241)
        self.assertLessEqual(max(generated), paint.DEFAULT_MAX_COMPONENT_COMMITS)
        # Replacing the largest old/new component plus old/new main tips.
        self.assertLessEqual(2 * max(generated) + 2, 750)

    def test_legacy_component_intensity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "1,201 commits"):
            paint.component_plan(
                paint.DEFAULT_MESSAGE,
                date(2026, 7, 1),
                "00-h",
                100,
                paint.DEFAULT_MAX_COMPONENT_COMMITS,
            )

    def test_unsupported_character_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "unsupported message character"):
            paint.build_components("Hi?")

    def test_message_requires_a_lit_glyph(self):
        with self.assertRaisesRegex(ValueError, "at least one lit glyph"):
            paint.build_components("   ")

    def test_stream_contains_one_component_plus_bot_restore(self):
        args = argparse.Namespace(
            message=paint.DEFAULT_MESSAGE,
            end_date=date(2026, 7, 1),
            commits_per_pixel=paint.DEFAULT_COMMITS_PER_PIXEL,
            max_commits=paint.DEFAULT_MAX_COMPONENT_COMMITS,
            component="00-h",
            name="James Feore",
            email="jjfeore@gmail.com",
            branch="paint-rebuild",
            root="1" * 40,
            head_tree="2" * 40,
        )
        stream = io.BytesIO()

        paint.emit_stream(stream, args)
        output = stream.getvalue()

        self.assertEqual(output.count(b"commit refs/heads/paint-rebuild\n"), 241)
        self.assertIn(b"from " + b"1" * 40 + b"\n", output)
        self.assertIn(b'M 040000 ' + b"2" * 40 + b' ""\n', output)
        self.assertIn(
            b"author github-actions[bot] "
            b"<41898282+github-actions[bot]@users.noreply.github.com>",
            output,
        )
        marker = paint.component_marker(
            paint.DEFAULT_MESSAGE,
            "00-h",
            date(2026, 7, 1),
            paint.DEFAULT_COMMITS_PER_PIXEL,
        ).encode()
        self.assertIn(marker, output)
        self.assertTrue(output.endswith(b"done\n"))

    @unittest.skipIf(
        os.name == "nt",
        "the bundled Windows test runtime cannot create sandboxed Git metadata",
    )
    def test_stream_imports_and_restores_the_fixed_tree(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as repo:
            self.git(repo, "init", "-q")
            Path(repo, "README.md").write_text("profile\n", encoding="utf-8")
            self.git(repo, "add", "README.md")
            self.git(
                repo,
                "-c",
                "user.name=Test User",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-q",
                "-m",
                "root",
            )
            root = self.git(repo, "rev-parse", "HEAD")
            tree = self.git(repo, "rev-parse", "HEAD^{tree}")
            args = argparse.Namespace(
                message=paint.DEFAULT_MESSAGE,
                end_date=date(2026, 7, 1),
                commits_per_pixel=paint.DEFAULT_COMMITS_PER_PIXEL,
                max_commits=paint.DEFAULT_MAX_COMPONENT_COMMITS,
                component="00-h",
                name="James Feore",
                email="jjfeore@gmail.com",
                branch="paint-rebuild",
                root=root,
                head_tree=tree,
            )
            stream = io.BytesIO()
            paint.emit_stream(stream, args)

            self.git(
                repo,
                "fast-import",
                "--force",
                "--quiet",
                input_bytes=stream.getvalue(),
            )

            generated = self.git(
                repo, "rev-list", "--count", f"{root}..paint-rebuild"
            )
            restored_tree = self.git(repo, "rev-parse", "paint-rebuild^{tree}")
            self.assertEqual(generated, "241")
            self.assertEqual(restored_tree, tree)


if __name__ == "__main__":
    unittest.main()
