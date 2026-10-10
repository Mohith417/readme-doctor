import os
import unittest
from unittest.mock import patch

from readme_doctor.analyzer import generate_readme
from readme_doctor.factcheck import check_readme
from readme_doctor.layout import build_badges, build_tree

REPO = {"name": "demo", "owner": "me", "description": "d", "language": "Python", "stars": 1,
        "readme": "# Old\n", "file_structure": ["app.py", "LICENSE", "docs/logo.png", ".github/workflows/ci.yml"],
        "code_samples": {"app.py": "print(1)"}}


class Badges(unittest.TestCase):
    def test_a_repo_with_everything_gets_four_true_badges_in_order(self):
        base = "me/demo"
        link = f"https://github.com/{base}/actions/workflows/ci.yml"
        self.assertEqual(build_badges(REPO), [
            f"[![ci]({link}/badge.svg)]({link})",
            f"![License](https://img.shields.io/github/license/{base})",
            f"![Top language](https://img.shields.io/github/languages/top/{base})",
            f"![Stars](https://img.shields.io/github/stars/{base}?style=flat)",
        ])

    def test_nothing_is_claimed_that_the_repo_does_not_have(self):
        bare = dict(REPO, file_structure=["app.py"], language=None)
        self.assertEqual(build_badges(bare), ["![Stars](https://img.shields.io/github/stars/me/demo?style=flat)"])

    def test_a_license_file_in_a_subfolder_does_not_count(self):
        badges = build_badges(dict(REPO, file_structure=["docs/LICENSE"]))
        self.assertFalse(any("License" in b for b in badges))

    def test_only_real_workflow_files_get_a_build_badge(self):
        files = [".github/workflows/notes.txt", ".github/workflows/deep/x.yml", "ci.yml", ".github/workflows/test.yaml"]
        badges = build_badges(dict(REPO, file_structure=files))
        self.assertEqual(sum("actions/workflows" in b for b in badges), 1)
        self.assertTrue(any("test.yaml/badge.svg" in b for b in badges))

    def test_unknown_owner_means_no_badges_at_all(self):
        self.assertEqual(build_badges(dict(REPO, owner="unknown")), [])
        self.assertEqual(build_badges(dict(REPO, owner=None)), [])


class Tree(unittest.TestCase):
    def test_exact_small_example(self):
        files = ["app.py", "README.md", "src/core.py", "src/util.py", "tests/test_a.py"]
        self.assertEqual(build_tree(files, "demo"), "\n".join([
            "demo/",
            "├── src/",
            "│   ├── core.py",
            "│   └── util.py",
            "├── tests/",
            "│   └── test_a.py",
            "├── app.py",
            "└── README.md",
        ]))

    def test_only_two_levels_are_shown(self):
        text = build_tree(["a/b/c/d.txt", "a/b/e.txt"], "demo")
        self.assertIn("a/", text)
        self.assertIn("b/", text)
        self.assertNotIn("c/", text)
        self.assertNotIn("d.txt", text)

    def test_generated_and_installed_folders_are_left_out(self):
        files = ["app.py", "node_modules/x/y.js", "venv/lib/z.py", "pkg/__pycache__/m.pyc", "build/out.js", "pkg/m.py"]
        text = build_tree(files, "demo")
        for junk in ("node_modules", "venv", "__pycache__", ".pyc", "build"):
            self.assertNotIn(junk, text)
        self.assertIn("m.py", text)

    def test_a_huge_repo_is_cut_to_the_line_limit_with_a_note(self):
        lines = build_tree([f"f{i:03}.py" for i in range(100)], "demo").splitlines()
        self.assertEqual(len(lines), 30)
        self.assertRegex(lines[-1], r"^… \(\d+ more entries\)$")

    def test_no_files_gives_just_the_root(self):
        self.assertEqual(build_tree([], "demo"), "demo/")


class FakeResp:
    status_code, headers = 200, {}

    def __init__(self, content):
        self.text = self._c = content

    def json(self):
        return {"choices": [{"message": {"content": self._c}}]}


def prompt_for(data):
    seen = []

    def post(url, headers=None, json=None, timeout=None):
        seen.append(json["messages"][0]["content"])
        return FakeResp("# Demo")
    with patch.dict(os.environ, {"GROQ_API_KEY": "k"}), patch("readme_doctor.analyzer.requests.post", post):
        generate_readme(dict(data))
    return seen[0]


class InThePrompt(unittest.TestCase):
    def test_the_real_badges_and_tree_are_handed_to_the_writer_word_for_word(self):
        prompt = prompt_for(REPO)
        for badge in build_badges(REPO):
            self.assertIn(badge, prompt)
        self.assertIn(build_tree(REPO["file_structure"], "demo"), prompt)
        for needle in ('<div align="center">', "add no others", "<details><summary>", "never invent facts"):
            self.assertIn(needle, prompt)

    def test_unknown_owner_tells_the_writer_to_add_no_badges(self):
        self.assertIn("(none - add no badges)", prompt_for(dict(REPO, owner="unknown")))

    def test_no_file_list_means_no_made_up_tree(self):
        self.assertIn("(not available)", prompt_for(dict(REPO, file_structure=[])))


class HtmlImagesAndLinks(unittest.TestCase):
    def found(self, text):
        return {(f.kind, f.claim) for f in check_readme(text, REPO)[0]}

    def test_a_missing_logo_in_the_header_is_flagged(self):
        self.assertEqual(self.found('<p align="center"><img src="assets/logo.png" width="120"></p>'), {("link", "assets/logo.png")})

    def test_a_real_logo_and_web_images_are_fine(self):
        text = '<img src="docs/logo.png"> <img src=\'https://img.shields.io/badge/a-b-green\'> <a href="LICENSE">License</a> <a href="#usage">Top</a>'
        self.assertEqual(self.found(text), set())

    def test_markdown_images_to_missing_files_are_flagged(self):
        self.assertEqual(self.found("![screenshot](docs/screenshot.png) ![logo](docs/logo.png)"), {("link", "docs/screenshot.png")})

    def test_a_missing_html_link_is_flagged(self):
        self.assertEqual(self.found('<a href="CONTRIBUTING.md">Contribute</a>'), {("link", "CONTRIBUTING.md")})


if __name__ == "__main__":
    unittest.main()