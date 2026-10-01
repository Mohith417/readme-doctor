import base64
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import requests

from readme_doctor import fetcher
from readme_doctor.fetcher import (
    RepoFetchError,
    fetch_repo_data,
    input_budget_chars,
    make_outline,
    pack_context,
    parse_repo_url,
    select_files,
)
from readme_doctor.scorer import get_grade, parse_score


class FakeResponse:
    def __init__(self, status_code, data=None, content=b""):
        self.status_code = status_code
        self._data = data or {}
        self.content = content

    def json(self):
        return self._data


def fake_github(repo_status=200, files=(), file_text=None, calls=None, readme_status=200):
    """Fake requests.get that mimics GitHub. files: list of path or (path, size). No internet used."""
    entries = [(f, 100) if isinstance(f, str) else f for f in files]

    def fake_get(url, headers=None, timeout=None):
        if calls is not None:
            calls.append(url)
        if "raw.githubusercontent.com" in url:
            text = file_text if file_text is not None else "x = 1\n"
            return FakeResponse(200, content=text.encode())
        if url.endswith("/readme"):
            if readme_status != 200:
                return FakeResponse(readme_status)
            return FakeResponse(200, {"content": base64.b64encode("# Hello ✓".encode()).decode()})
        if "git/trees" in url:
            return FakeResponse(200, {"tree": [{"type": "blob", "path": p, "size": s} for p, s in entries]})
        return FakeResponse(repo_status, {
            "name": "demo", "owner": {"login": "me"}, "description": "A demo",
            "stargazers_count": 3, "language": "Python",
        })
    return fake_get


def fetch(**kwargs):
    with patch("readme_doctor.fetcher.requests.get", fake_github(**kwargs)):
        return fetch_repo_data("https://github.com/me/demo")


class UrlParsing(unittest.TestCase):
    def test_accepted_url_styles(self):
        for url in ["https://github.com/me/demo", "https://github.com/me/demo/",
                    "https://github.com/me/demo.git", "https://github.com/me/demo/tree/main/src",
                    "github.com/me/demo"]:
            with self.subTest(url=url):
                self.assertEqual(parse_repo_url(url), ("me", "demo"))

    def test_rejected_urls(self):
        for url in ["https://gitlab.com/me/demo", "https://github.com/onlyowner", "hello"]:
            with self.subTest(url=url):
                with self.assertRaises(RepoFetchError):
                    parse_repo_url(url)


class FileSelection(unittest.TestCase):
    def test_important_files_come_first_and_junk_is_skipped(self):
        entries = [
            ("README.md", 10), ("logo.png", 10),
            ("node_modules/lib/x.js", 10), ("venv/lib/y.py", 10),
            ("docs/conf.py", 500), ("examples/demo.py", 500), ("tests/test_core.py", 500),
            ("src/pkg/small.py", 100), ("src/pkg/core.py", 9000),
            ("app.py", 50), ("requirements.txt", 20),
        ]
        order = select_files(entries)
        self.assertEqual(order[:4], ["requirements.txt", "app.py", "src/pkg/core.py", "src/pkg/small.py"])
        self.assertEqual(set(order[4:]), {"docs/conf.py", "examples/demo.py", "tests/test_core.py"})
        for junk in ("README.md", "logo.png", "node_modules/lib/x.js", "venv/lib/y.py"):
            self.assertNotIn(junk, order)

    def test_huge_files_are_skipped(self):
        self.assertEqual(select_files([("big.py", 10_000_000), ("ok.py", 10)]), ["ok.py"])

    def test_large_real_source_files_are_kept(self):
        # click's core.py is 152,537 bytes and used to be skipped by mistake
        self.assertIn("src/click/core.py", select_files([("src/click/core.py", 152_537), ("a.py", 10)]))

    def test_total_download_is_capped(self):
        entries = [(f"src/f{i}.py", 400_000) for i in range(20)]
        self.assertEqual(len(select_files(entries)), 15)

    def test_never_more_than_the_file_limit(self):
        entries = [(f"src/f{i}.py", 100) for i in range(200)]
        self.assertEqual(len(select_files(entries)), fetcher.MAX_FILES_TOTAL)


class Outline(unittest.TestCase):
    PY = "import os\n\nclass Repo:\n    def fetch(self):\n        x = 1\n        return x\n\n@app.route('/')\ndef home():\n    pass\n"
    JS = "const a = 1;\nexport function run() {}\napp.get('/x', handler);\nlet y = 2;\n"

    def test_keeps_definitions_only(self):
        out = make_outline(self.PY, 400).splitlines()
        self.assertEqual(out, ["class Repo:", "    def fetch(self):", "@app.route('/')", "def home():"])
        self.assertEqual(make_outline(self.JS, 400).splitlines(), ["export function run() {}", "app.get('/x', handler);"])

    def test_respects_size_limit(self):
        self.assertLessEqual(len(make_outline("def a():\n" * 500, 100)), 100)


class RepoReading(unittest.TestCase):
    def test_repo_with_no_code_files_still_returns_data(self):
        data = fetch(files=["README.md", "logo.png"])
        self.assertEqual(data["code_samples"], {})
        self.assertEqual(data["readme"], "# Hello ✓")

    def test_files_are_read_in_full_not_cut(self):
        big = "print('line')\n" * 5000                      # 70,000 characters
        data = fetch(files=["app.py"], file_text=big)
        self.assertEqual(data["code_samples"]["app.py"], big)

    def test_files_come_back_best_first(self):
        data = fetch(files=["tests/test_a.py", "src/core.py", "app.py", "requirements.txt"])
        self.assertEqual(list(data["code_samples"])[:3], ["requirements.txt", "app.py", "src/core.py"])

    def test_full_file_list_is_returned_not_cut_at_50(self):
        data = fetch(files=[f"src/f{i}.py" for i in range(120)])
        self.assertEqual(len(data["file_structure"]), 120)

    def test_reads_at_most_the_file_limit(self):
        calls = []
        fetch(files=[f"src/f{i}.py" for i in range(150)], calls=calls)
        raw = [c for c in calls if "raw.githubusercontent.com" in c]
        self.assertEqual(len(raw), fetcher.MAX_FILES_TOTAL)

    def test_file_never_downloaded_when_too_big(self):
        calls = []
        fetch(files=[("huge.py", 10_000_000), ("ok.py", 10)], calls=calls)
        raw = [c for c in calls if "raw.githubusercontent.com" in c]
        self.assertEqual(len(raw), 1)
        self.assertTrue(raw[0].endswith("ok.py"))


class PackContext(unittest.TestCase):
    FILES = {
        "app.py": "def home():\n    return 1\n",
        "core.py": "class Core:\n    def run(self):\n        pass\n" + "# filler\n" * 400,
        "util.py": "def helper():\n    pass\n",
    }

    def test_everything_fits_when_budget_is_large(self):
        text, stats = pack_context(self.FILES, 1_000_000)
        self.assertEqual(stats, {"full": 3, "outline": 0, "skipped": 0})
        self.assertIn("# filler", text)

    def test_big_file_becomes_outline_but_small_files_stay_whole(self):
        text, stats = pack_context(self.FILES, 600)
        self.assertEqual(stats["full"], 2)
        self.assertEqual(stats["outline"], 1)
        self.assertIn("### core.py (outline only)", text)
        self.assertIn("def run(self):", text)
        self.assertNotIn("# filler", text)
        self.assertLessEqual(len(text), 600)

    def test_never_exceeds_the_budget(self):
        files = {f"f{i}.py": "def f():\n    pass\n" * 200 for i in range(40)}
        for budget in (500, 3000, 12000):
            with self.subTest(budget=budget):
                text, stats = pack_context(files, budget)
                self.assertLessEqual(len(text), budget)
                self.assertEqual(sum(stats.values()), 40)

    def test_order_is_kept_so_best_files_win(self):
        files = {"best.py": "a = 1\n" * 30, "worst.py": "b = 2\n" * 30}
        text, stats = pack_context(files, 260)
        self.assertIn("### best.py", text)
        self.assertNotIn("### worst.py", text)
        self.assertEqual(stats["skipped"], 1)


class Budget(unittest.TestCase):
    def test_free_plan_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GROQ_TPM_LIMIT", None)
            self.assertEqual(input_budget_chars(4000), 12000)

    def test_paid_plan_gets_far_more(self):
        with patch.dict(os.environ, {"GROQ_TPM_LIMIT": "250000"}):
            self.assertEqual(input_budget_chars(4000), 738000)

    def test_bad_value_falls_back_to_default(self):
        with patch.dict(os.environ, {"GROQ_TPM_LIMIT": "lots"}):
            self.assertEqual(input_budget_chars(4000), 12000)


class ErrorHandling(unittest.TestCase):
    def test_cli_mode_prints_and_returns_none(self):
        out = io.StringIO()
        with patch("readme_doctor.fetcher.requests.get", fake_github(repo_status=404)):
            with redirect_stdout(out):
                result = fetch_repo_data("https://github.com/me/missing")
        self.assertIsNone(result)
        self.assertIn("Repo not found", out.getvalue())

    def test_web_mode_raises_clear_messages(self):
        expected = {404: "Repo not found", 403: "rate limit", 401: "rejected the token"}
        for status, text in expected.items():
            with self.subTest(status=status):
                with patch("readme_doctor.fetcher.requests.get", fake_github(repo_status=status)):
                    with self.assertRaises(RepoFetchError) as ctx:
                        fetch_repo_data("https://github.com/me/demo", raise_errors=True)
                self.assertIn(text, str(ctx.exception))

    def test_network_down_gives_clear_message_instead_of_a_crash(self):
        with patch("readme_doctor.fetcher.requests.get", side_effect=requests.ConnectionError("down")):
            with self.assertRaises(RepoFetchError) as ctx:
                fetch_repo_data("https://github.com/me/demo", raise_errors=True)
            self.assertIn("Could not reach GitHub", str(ctx.exception))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertIsNone(fetch_repo_data("https://github.com/me/demo"))
            self.assertIn("Could not reach GitHub", out.getvalue())

    def test_repo_without_readme(self):
        self.assertEqual(fetch(readme_status=404)["readme"], "No README found")


class Scoring(unittest.TestCase):
    REAL_REPORT = "SCORE: 55\nSUMMARY: ok\nISSUES:\n- a\nSUGGESTIONS:\n- b\n"

    def test_score_and_grade_from_real_click_output(self):
        self.assertEqual(parse_score(self.REAL_REPORT), 55)
        self.assertEqual(get_grade(55)[0], "D")

    def test_missing_score_gives_none(self):
        self.assertIsNone(parse_score("no score here"))


if __name__ == "__main__":
    unittest.main()