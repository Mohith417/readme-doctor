import unittest

from readme_doctor.rubric import evaluate_readme, issues, suggestions

GOOD = """# Demo Tool

![License](https://img.shields.io/badge/license-MIT-green.svg)

## About
Demo Tool checks things for you. It solves the problem of manual checking, saves time, and is built for
developers who want quick answers without reading every file by hand. It works on any project size.

The tool reads your project, applies a fixed set of rules, and prints a short report. Reports are plain text,
so they are easy to paste into an issue, a pull request or a chat message, and they never change between runs
for the same input. Configuration is optional, and sensible defaults are used when nothing is set.

## Features
- Fast
- Simple

## Prerequisites
Python 3.10+ is required.

## Installation
```bash
git clone https://github.com/me/demo.git
pip install -r requirements.txt
```

## Usage
```bash
demo run --fast
```

## Troubleshooting
If you see an error, re-run the install step.

## Contributing
Pull requests are welcome.

## License
MIT License.
"""


def score(text, files=()):
    return evaluate_readme(text, files)["score"]


class Basics(unittest.TestCase):
    def test_points_add_up_to_100(self):
        checks = evaluate_readme(GOOD)["checks"]
        self.assertEqual(sum(c.points for c in checks), 100)

    def test_complete_readme_gets_full_marks(self):
        self.assertEqual(score(GOOD), 100)

    def test_tiny_readme_scores_very_low(self):
        self.assertLess(score("# foo\nthis is a tool\n"), 20)

    def test_no_readme_scores_zero(self):
        for text in ("No README found", "", "   "):
            result = evaluate_readme(text)
            self.assertEqual(result["score"], 0)
            self.assertEqual(issues(result), ["The repository has no README file."])

    def test_same_input_always_same_score(self):
        self.assertEqual({score(GOOD, ["LICENSE"]) for _ in range(10)}, {100})
        tiny = "# foo\nthis is a tool\n"
        self.assertEqual({score(tiny) for _ in range(10)}, {score(tiny)})


class ReadingMarkdownCorrectly(unittest.TestCase):
    def test_hash_comments_inside_code_blocks_are_not_headings(self):
        text = "Just text.\n\n```bash\n# Install\n# Usage\n# License\n```\n"
        result = evaluate_readme(text)
        passed = {c.key for c in result["checks"] if c.passed}
        for key in ("title", "install_section", "usage_section", "license"):
            self.assertNotIn(key, passed)

    def test_html_headings_count(self):
        text = '<h1 align="center">Demo</h1>\n<h2>Installation</h2>\n<h2>Usage</h2>\n'
        passed = {c.key for c in evaluate_readme(text)["checks"] if c.passed}
        self.assertTrue({"title", "install_section", "usage_section", "structure"} <= passed)


class RepoFiles(unittest.TestCase):
    BARE = "# Demo\n\nSome text about the demo. " * 5

    def test_license_file_gives_license_credit(self):
        self.assertEqual(score(self.BARE, ["LICENSE"]) - score(self.BARE), 8)
        self.assertEqual(score(self.BARE, ["LICENSE.txt"]) - score(self.BARE), 8)

    def test_contributing_file_gives_contributing_credit(self):
        self.assertEqual(score(self.BARE, ["CONTRIBUTING.md"]) - score(self.BARE), 7)

    def test_unrelated_files_give_nothing(self):
        self.assertEqual(score(self.BARE, ["app.py", "notes.txt"]), score(self.BARE))


class IssueLists(unittest.TestCase):
    def test_every_failed_check_has_an_issue_and_a_fix(self):
        result = evaluate_readme("# foo\nhello\n")
        failed = [c for c in result["checks"] if not c.passed]
        self.assertEqual(len(issues(result)), len(failed))
        self.assertEqual(len(suggestions(result)), len(failed))

    def test_complete_readme_has_no_issues(self):
        self.assertEqual(issues(evaluate_readme(GOOD)), [])

    def test_biggest_gaps_listed_first(self):
        result = evaluate_readme("# foo\nhello\n")
        order = [c.points for c in sorted([c for c in result["checks"] if not c.passed], key=lambda c: -c.points)]
        self.assertEqual(order, sorted(order, reverse=True))
        self.assertIn("installation", issues(result)[0].lower() + issues(result)[1].lower() + issues(result)[2].lower())


if __name__ == "__main__":
    unittest.main()