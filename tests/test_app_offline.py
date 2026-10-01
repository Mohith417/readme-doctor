import os
import unittest
from unittest.mock import patch

import app as webapp
from readme_doctor.fetcher import RepoFetchError

# The exact report format your CLI printed for pallets/click.
REAL_REPORT = """SCORE: 55
SUMMARY: The README includes a clear title and a helpful usage example, but it lacks installation instructions. Formatting is generally readable.
ISSUES:
- No installation or setup instructions are provided.
- There is no license section indicating the project's licensing terms.
SUGGESTIONS:
- Add an "Installation" section with pip commands.
- Include a brief "Why Click?" section.
"""

FAKE_REPO = {
    "name": "click", "owner": "pallets", "description": "CLI toolkit", "stars": 17779,
    "language": "Python", "readme": "# click", "file_structure": [], "code_samples": {},
}

URL = {"url": "https://github.com/pallets/click"}


class WebTestCase(unittest.TestCase):
    def setUp(self):
        webapp._hits.clear()          # fresh rate limit for every test
        self.client = webapp.app.test_client()


class ReportParsing(unittest.TestCase):
    def test_real_click_report(self):
        parts = webapp.parse_report(REAL_REPORT)
        self.assertTrue(parts["summary"].startswith("The README includes"))
        self.assertEqual(len(parts["issues"]), 2)
        self.assertEqual(len(parts["suggestions"]), 2)
        self.assertEqual(parts["issues"][0], "No installation or setup instructions are provided.")

    def test_bold_markdown_variant(self):
        text = "**SCORE:** 70\n**SUMMARY:** ok\n**ISSUES:**\n- **A**: x\n**SUGGESTIONS:**\n- y"
        parts = webapp.parse_report(text)
        self.assertEqual(parts["issues"], ["A: x"])
        self.assertEqual(parts["suggestions"], ["y"])


class Routes(WebTestCase):
    def test_health(self):
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})

    def test_analyze_success(self):
        with patch("app.fetch_repo_data", return_value=FAKE_REPO), \
             patch("app.analyze_readme", return_value=REAL_REPORT):
            r = self.client.post("/api/analyze", json=URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["name"], "click")
        self.assertEqual(r.json["score"], 55)
        self.assertEqual(r.json["grade"], "D")
        self.assertEqual(len(r.json["issues"]), 2)

    def test_analyze_without_a_score_gives_na(self):
        with patch("app.fetch_repo_data", return_value=FAKE_REPO), \
             patch("app.analyze_readme", return_value="no score here"):
            r = self.client.post("/api/analyze", json=URL)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json["score"])
        self.assertEqual(r.json["grade"], "N/A")

    def test_generate_success(self):
        with patch("app.fetch_repo_data", return_value=FAKE_REPO), \
             patch("app.generate_readme", return_value="# New README"):
            r = self.client.post("/api/generate", json=URL)
        self.assertEqual(r.json, {"readme": "# New README", "name": "click"})


class Errors(WebTestCase):
    def test_empty_url(self):
        r = self.client.post("/api/analyze", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("GitHub repo URL", r.json["error"])

    def test_repo_not_found(self):
        msg = "Repo not found. Check the URL, or add a GitHub token if the repo is private."
        with patch("app.fetch_repo_data", side_effect=RepoFetchError(msg)):
            r = self.client.post("/api/analyze", json=URL)
        self.assertEqual((r.status_code, r.json["error"]), (400, msg))

    def test_github_unreachable(self):
        with patch("app.fetch_repo_data", side_effect=ConnectionError("down")):
            r = self.client.post("/api/analyze", json=URL)
        self.assertEqual(r.status_code, 502)
        self.assertIn("Could not reach GitHub", r.json["error"])

    def test_ai_down_on_analyze_and_generate(self):
        with patch("app.fetch_repo_data", return_value=FAKE_REPO), \
             patch("app.analyze_readme", return_value=None), \
             patch("app.generate_readme", return_value=None):
            a = self.client.post("/api/analyze", json=URL)
            g = self.client.post("/api/generate", json=URL)
        for r in (a, g):
            self.assertEqual(r.status_code, 502)
            self.assertIn("AI service did not respond", r.json["error"])

    def test_rate_limit_blocks_the_sixth_request(self):
        codes = [self.client.post("/api/analyze", json={}).status_code for _ in range(7)]
        self.assertEqual(codes, [400, 400, 400, 400, 400, 429, 429])


class TokenHandling(WebTestCase):
    def tokens_used(self, body):
        seen = []

        def fake_fetch(url, token, raise_errors=False):
            seen.append(token)
            return FAKE_REPO

        with patch.dict(os.environ, {"GITHUB_TOKEN": "PERSONAL", "WEB_GITHUB_TOKEN": "SERVER_PUBLIC"}), \
             patch("app.fetch_repo_data", side_effect=fake_fetch), \
             patch("app.analyze_readme", return_value=REAL_REPORT):
            self.client.post("/api/analyze", json=body)
        return seen

    def test_server_uses_public_token_never_the_personal_one(self):
        self.assertEqual(self.tokens_used(URL), ["SERVER_PUBLIC"])

    def test_visitor_token_wins(self):
        self.assertEqual(self.tokens_used({**URL, "token": "VISITOR"}), ["VISITOR"])


if __name__ == "__main__":
    unittest.main()