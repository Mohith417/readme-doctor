import os
import unittest
from unittest.mock import patch

import requests

from readme_doctor import analyzer
from readme_doctor.analyzer import AIServiceError, analyze_readme, generate_readme
from readme_doctor.scorer import parse_score

AI_REPLY = """SUMMARY: A clear README for newcomers.
PROBLEMS:
- The README says to run `old.py` but that file does not exist.
SUGGESTIONS:
- Add a screenshot of the output.
"""
README = "# Demo\n\nSome words about the demo project. " * 8 + "\n\n## Installation\n```bash\npip install demo\n```\n"


class FakeResp:
    def __init__(self, status=200, content="ok", headers=None, text=None):
        self.status_code = status
        self.headers = headers or {}
        self._content = content
        self.text = text if text is not None else (content or "")

    def json(self):
        if self.status_code != 200:
            raise ValueError("not json")
        return {"choices": [{"message": {"content": self._content}}]}


class FakeGroq:
    """Stand-in for requests.post. The last response repeats when the list runs out."""
    def __init__(self, *responses):
        self.responses = list(responses) or [FakeResp(200, AI_REPLY)]
        self.bodies = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.bodies.append(json)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]

    @property
    def prompts(self):
        return [b["messages"][0]["content"] for b in self.bodies]


class Env(unittest.TestCase):
    def run_with(self, fake, func, *args, env=None, **kwargs):
        values = {"GROQ_API_KEY": "test-key"}
        values.update(env or {})
        with patch.dict(os.environ, values), \
             patch("readme_doctor.analyzer.requests.post", fake), \
             patch("readme_doctor.analyzer.time.sleep") as sleep:
            self.sleep = sleep
            return func(*args, **kwargs)


class Reliability(Env):
    REPO = {"name": "demo", "owner": "me", "description": "d", "language": "Python", "stars": 1,
            "readme": README, "file_structure": ["app.py"], "code_samples": {"app.py": "print(1)"}}

    def test_success_returns_text(self):
        self.assertEqual(self.run_with(FakeGroq(FakeResp(200, "# New")), generate_readme, self.REPO), "# New")

    def test_missing_key_gives_clear_error(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            with self.assertRaises(AIServiceError) as ctx:
                generate_readme(self.REPO, raise_errors=True)
        self.assertIn("GROQ_API_KEY", str(ctx.exception))

    def test_busy_then_ok_waits_and_succeeds(self):
        fake = FakeGroq(FakeResp(429, headers={"retry-after": "7"}, text="rate limit"), FakeResp(200, "# New"))
        self.assertEqual(self.run_with(fake, generate_readme, self.REPO), "# New")
        self.sleep.assert_called_once_with(7.0)

    def test_wait_time_is_capped(self):
        fake = FakeGroq(FakeResp(429, headers={"retry-after": "500"}, text="rate limit"), FakeResp(200, "# New"))
        self.run_with(fake, generate_readme, self.REPO)
        self.sleep.assert_called_once_with(float(analyzer.MAX_WAIT_SECONDS))

    def test_always_busy_gives_busy_message(self):
        fake = FakeGroq(FakeResp(429, text="rate limit"))
        with self.assertRaises(AIServiceError) as ctx:
            self.run_with(fake, generate_readme, self.REPO, raise_errors=True)
        self.assertIn("busy", str(ctx.exception))
        self.assertEqual(len(fake.bodies), analyzer.MAX_ATTEMPTS)

    def test_too_large_retries_with_less_content(self):
        repo = dict(self.REPO, code_samples={f"f{i}.py": "def work():\n    pass\n" * 25 for i in range(10)})
        finals = []

        def post(url, headers=None, json=None, timeout=None):
            prompt = json["messages"][0]["content"]
            if "Generate a complete README.md" in prompt:
                finals.append(prompt)
                return FakeResp(413, text="Request too large") if len(finals) == 1 else FakeResp(200, "# New")
            return FakeResp(200, "NOTES: short")

        self.assertEqual(self.run_with(post, generate_readme, repo), "# New")
        self.assertEqual(len(finals), 2)
        self.assertLess(len(finals[1]), len(finals[0]))

    def test_always_too_large_gives_clear_error(self):
        fake = FakeGroq(FakeResp(413, text="Request too large"))
        with self.assertRaises(AIServiceError) as ctx:
            self.run_with(fake, generate_readme, self.REPO, raise_errors=True)
        self.assertIn("too large", str(ctx.exception))
        self.assertEqual(len(fake.bodies), 3)

    def test_network_error(self):
        def boom(*a, **k):
            raise requests.ConnectionError("down")
        with self.assertRaises(AIServiceError) as ctx:
            self.run_with(boom, generate_readme, self.REPO, raise_errors=True)
        self.assertIn("Could not reach the AI service", str(ctx.exception))

    def test_empty_answer(self):
        with self.assertRaises(AIServiceError) as ctx:
            self.run_with(FakeGroq(FakeResp(200, None)), generate_readme, self.REPO, raise_errors=True)
        self.assertIn("empty", str(ctx.exception))

    def test_rejected_key(self):
        with self.assertRaises(AIServiceError) as ctx:
            self.run_with(FakeGroq(FakeResp(401, text="bad key")), generate_readme, self.REPO, raise_errors=True)
        self.assertIn("rejected", str(ctx.exception))

    def test_server_error_then_ok(self):
        fake = FakeGroq(FakeResp(503, text="oops"), FakeResp(200, "# New"))
        self.assertEqual(self.run_with(fake, generate_readme, self.REPO), "# New")

    def test_cli_mode_returns_none_instead_of_raising(self):
        self.assertIsNone(self.run_with(FakeGroq(FakeResp(429, text="x")), generate_readme, self.REPO))


class Analyze(Env):
    def score_of(self, report):
        return parse_score(report)

    def test_score_never_changes_whatever_the_ai_says(self):
        a = self.run_with(FakeGroq(FakeResp(200, AI_REPLY)), analyze_readme, README)
        b = self.run_with(FakeGroq(FakeResp(200, "SUMMARY: Totally different words.\nPROBLEMS:\n- none\nSUGGESTIONS:\n- Other idea.")), analyze_readme, README)
        c = self.run_with(FakeGroq(FakeResp(500, text="down")), analyze_readme, README)
        self.assertEqual({self.score_of(a), self.score_of(b), self.score_of(c)}, {self.score_of(a)})

    def test_temperature_is_zero_for_analysis(self):
        fake = FakeGroq()
        self.run_with(fake, analyze_readme, README)
        self.assertEqual(fake.bodies[0]["temperature"], 0)

    def test_report_has_all_four_sections_in_order(self):
        report = self.run_with(FakeGroq(), analyze_readme, README)
        positions = [report.index(k) for k in ("SCORE:", "SUMMARY:", "ISSUES:", "SUGGESTIONS:")]
        self.assertEqual(positions, sorted(positions))

    def test_ai_text_is_merged_with_checklist_findings(self):
        report = self.run_with(FakeGroq(), analyze_readme, README)
        self.assertIn("A clear README for newcomers.", report)
        self.assertIn("does not exist", report)              # the AI's README-vs-code problem
        self.assertIn("Add a screenshot", report)
        self.assertIn("license information", report.lower())  # the checklist's own finding

    def test_none_problems_are_dropped(self):
        reply = "SUMMARY: ok\nPROBLEMS:\n- none\nSUGGESTIONS:\n- Do X."
        report = self.run_with(FakeGroq(FakeResp(200, reply)), analyze_readme, README)
        self.assertNotIn("- none", report.lower())

    def test_ai_down_still_returns_score_and_issues(self):
        report = self.run_with(FakeGroq(FakeResp(429, text="busy")), analyze_readme, README)
        self.assertIsNotNone(parse_score(report))
        self.assertIn("AI commentary is unavailable", report)
        self.assertIn("ISSUES:", report)

    def test_no_readme_makes_no_ai_call(self):
        fake = FakeGroq()
        report = self.run_with(fake, analyze_readme, "No README found")
        self.assertEqual(fake.bodies, [])
        self.assertEqual(parse_score(report), 0)

    def test_repo_files_change_the_score(self):
        plain = self.run_with(FakeGroq(), analyze_readme, README)
        with_license = self.run_with(FakeGroq(), analyze_readme, README, ["LICENSE"])
        self.assertEqual(parse_score(with_license) - parse_score(plain), 8)

    def test_whole_readme_is_sent_when_it_fits(self):
        text = README + "\nUNIQUE-END-MARKER\n"
        fake = FakeGroq()
        self.run_with(fake, analyze_readme, text)
        self.assertIn("UNIQUE-END-MARKER", fake.prompts[0])
        self.assertNotIn("middle omitted", fake.prompts[0])

    def test_huge_readme_is_trimmed_on_free_plan_but_not_on_paid(self):
        huge = README + ("filler line of documentation text\n" * 4000) + "\nUNIQUE-END-MARKER\n"
        free = FakeGroq()
        self.run_with(free, analyze_readme, huge, env={"GROQ_TPM_LIMIT": "8000"})
        self.assertIn("middle omitted", free.prompts[0])
        self.assertIn("UNIQUE-END-MARKER", free.prompts[0])          # the end is kept
        self.assertLess(len(free.prompts[0]), 20000)
        paid = FakeGroq()
        self.run_with(paid, analyze_readme, huge, env={"GROQ_TPM_LIMIT": "250000"})
        self.assertNotIn("middle omitted", paid.prompts[0])
        self.assertGreater(len(paid.prompts[0]), len(huge))

    def test_code_files_are_included_for_checking_the_readme(self):
        fake = FakeGroq()
        self.run_with(fake, analyze_readme, README, ["app.py"], {"app.py": "def special_marker(): pass"})
        self.assertIn("special_marker", fake.prompts[0])


class Generate(Env):
    REPO = {"name": "demo", "owner": "me", "description": None, "language": None, "stars": 0,
            "readme": README + "\nOLD-README-END-MARKER\n",
            "file_structure": ["src/core.py", "requirements.txt"],
            "code_samples": {"requirements.txt": "flask", "src/core.py": "def core_marker(): pass"}}

    def test_prompt_contains_whole_old_readme_files_and_structure(self):
        fake = FakeGroq(FakeResp(200, "# New"))
        self.run_with(fake, generate_readme, self.REPO)
        prompt = fake.prompts[0]
        for needle in ("OLD-README-END-MARKER", "core_marker", "src/core.py", "github.com/me/demo"):
            self.assertIn(needle, prompt)

    def test_a_long_old_readme_is_sent_in_full(self):
        long_readme = "Documentation sentence number one hundred.\n" * 55 + "OLD-README-END-MARKER\n"
        self.assertGreater(len(long_readme), 2000)
        fake = FakeGroq(FakeResp(200, "# New"))
        self.run_with(fake, generate_readme, dict(self.REPO, readme=long_readme))
        self.assertIn("OLD-README-END-MARKER", fake.prompts[0])

    def test_no_hard_coded_readme_doctor_commands_for_other_projects(self):
        fake = FakeGroq(FakeResp(200, "# New"))
        self.run_with(fake, generate_readme, self.REPO)
        self.assertNotIn("--score-only", fake.prompts[0])
        self.assertNotIn("readme-doctor <repo_url>", fake.prompts[0])

    def test_previous_feedback_is_included(self):
        fake = FakeGroq(FakeResp(200, "# New"))
        self.run_with(fake, generate_readme, dict(self.REPO, previous_feedback="ADD-A-LICENSE"))
        self.assertIn("ADD-A-LICENSE", fake.prompts[0])

    def test_markdown_wrapper_is_removed(self):
        out = self.run_with(FakeGroq(FakeResp(200, "```markdown\n# Title\n\ntext\n```")), generate_readme, self.REPO)
        self.assertEqual(out, "# Title\n\ntext")

    def test_missing_description_does_not_crash(self):
        self.assertEqual(self.run_with(FakeGroq(FakeResp(200, "# New")), generate_readme, self.REPO), "# New")


if __name__ == "__main__":
    unittest.main()