import base64
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from readme_doctor.fetcher import (
    RepoFetchError,
    fetch_repo_data,
    parse_repo_url,
)
from readme_doctor.scorer import get_grade, parse_score


class FakeResponse:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data


def fake_github(repo_status=200, files=()):
    """Return a fake requests.get that mimics the GitHub API (no internet used)."""
    def fake_get(url, headers=None):
        if url.endswith("/readme"):
            return FakeResponse(200, {"content": base64.b64encode(b"# Hello").decode()})
        if "git/trees" in url:
            return FakeResponse(200, {"tree": [{"type": "blob", "path": p} for p in files]})
        if "/contents/" in url:
            return FakeResponse(200, {"content": base64.b64encode(b"x = 1").decode()})
        return FakeResponse(repo_status, {
            "name": "demo", "owner": {"login": "me"}, "description": "A demo",
            "stargazers_count": 3, "language": "Python",
        })
    return fake_get


class UrlParsing(unittest.TestCase):
    def test_accepted_url_styles(self):
        for url in [
            "https://github.com/me/demo",
            "https://github.com/me/demo/",
            "https://github.com/me/demo.git",
            "https://github.com/me/demo/tree/main/src",
            "github.com/me/demo",
        ]:
            with self.subTest(url=url):
                self.assertEqual(parse_repo_url(url), ("me", "demo"))

    def test_rejected_urls(self):
        for url in ["https://gitlab.com/me/demo", "https://github.com/onlyowner", "hello"]:
            with self.subTest(url=url):
                with self.assertRaises(RepoFetchError):
                    parse_repo_url(url)


class CodeFileReading(unittest.TestCase):
    def read_samples(self, files):
        with patch("readme_doctor.fetcher.requests.get", fake_github(files=files)):
            return fetch_repo_data("https://github.com/me/demo")

    def test_repo_with_no_code_files_still_returns_data(self):
        data = self.read_samples([])
        self.assertIsNotNone(data)
        self.assertEqual(data["code_samples"], {})

    def test_reads_all_files_up_to_five(self):
        data = self.read_samples(["a.py", "b.py", "c.py", "d.py"])
        self.assertEqual(list(data["code_samples"]), ["a.py", "b.py", "c.py", "d.py"])

    def test_stops_at_five_files(self):
        data = self.read_samples([f"f{i}.py" for i in range(8)])
        self.assertEqual(len(data["code_samples"]), 5)


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


class Scoring(unittest.TestCase):
    REAL_REPORT = "SCORE: 55\nSUMMARY: ok\nISSUES:\n- a\nSUGGESTIONS:\n- b\n"

    def test_score_and_grade_from_real_click_output(self):
        self.assertEqual(parse_score(self.REAL_REPORT), 55)
        self.assertEqual(get_grade(55)[0], "D")

    def test_missing_score_gives_none(self):
        self.assertIsNone(parse_score("no score here"))


if __name__ == "__main__":
    unittest.main()