import os
import re
import unittest
from unittest.mock import patch

from readme_doctor import analyzer
from readme_doctor.analyzer import AIServiceError, analyze_readme, generate_readme

REPLY = "SUMMARY: Fine.\nPROBLEMS:\n- none\nSUGGESTIONS:\n- Add more examples.\n"


class FakeResp:
    def __init__(self, status=200, content="ok", text=None):
        self.status_code = status
        self.headers = {}
        self._content = content
        self.text = text if text is not None else (content or "")

    def json(self):
        if self.status_code != 200:
            raise ValueError("not json")
        return {"choices": [{"message": {"content": self._content}}]}


class Router:
    """Fake Groq: answers 'read this part' requests with short notes, everything else with REPLY."""
    def __init__(self, notes_status=200):
        self.prompts = []
        self.notes_status = notes_status

    def __call__(self, url, headers=None, json=None, timeout=None):
        prompt = json["messages"][0]["content"]
        self.prompts.append(prompt)
        match = re.search(r"README PART (\d+)/(\d+)", prompt)
        if match:
            if self.notes_status != 200:
                return FakeResp(self.notes_status, text="rate limit")
            return FakeResp(200, f"NOTES-{match.group(1)}: short version of this part")
        return FakeResp(200, REPLY if "SUMMARY:" in prompt else "# New README")

    @property
    def part_prompts(self):
        return [p for p in self.prompts if "README PART" in p]

    @property
    def final_prompt(self):
        return self.prompts[-1]


def make_readme(total_chars):
    """A README of about total_chars with markers at the start, middle and end."""
    line = "Documentation sentence that is long enough to count as real README text.\n"
    body = line * (total_chars // len(line))
    half = len(body) // 2
    return "# Demo\n\nSTART-MARKER\n" + body[:half] + "MIDDLE-MARKER\n" + body[half:] + "END-MARKER\n"


REPO = {"name": "demo", "owner": "me", "description": "d", "language": "Python", "stars": 1,
        "file_structure": ["app.py"], "code_samples": {"app.py": "def code_marker(): pass"}}


class Base(unittest.TestCase):
    def run_with(self, router, func, *args, env=None, **kwargs):
        values = {"GROQ_API_KEY": "test-key"}
        values.update(env or {})
        with patch.dict(os.environ, values), \
             patch("readme_doctor.analyzer.requests.post", router), \
             patch("readme_doctor.analyzer.time.sleep"):
            return func(*args, **kwargs)


class WordForWord(Base):
    def test_writer_gets_a_5000_char_readme_word_for_word_in_one_call(self):
        readme = make_readme(5000)
        router = Router()
        self.run_with(router, generate_readme, dict(REPO, readme=readme))
        self.assertEqual(len(router.prompts), 1)
        for marker in ("START-MARKER", "MIDDLE-MARKER", "END-MARKER"):
            self.assertIn(marker, router.final_prompt)
        self.assertNotIn("wrote these notes", router.final_prompt)     # it was not condensed

    def test_review_gets_a_10000_char_readme_word_for_word_in_one_call(self):
        router = Router()
        self.run_with(router, analyze_readme, make_readme(10000))
        self.assertEqual(len(router.prompts), 1)
        for marker in ("START-MARKER", "MIDDLE-MARKER", "END-MARKER"):
            self.assertIn(marker, router.final_prompt)

    def test_paid_plan_sends_even_a_long_readme_word_for_word(self):
        router = Router()
        self.run_with(router, generate_readme, dict(REPO, readme=make_readme(30000)), env={"GROQ_TPM_LIMIT": "250000"})
        self.assertEqual(len(router.prompts), 1)
        for marker in ("START-MARKER", "MIDDLE-MARKER", "END-MARKER"):
            self.assertIn(marker, router.final_prompt)


class EveryPartIsRead(Base):
    def assert_every_part_read(self, router):
        sent_to_ai = "\n".join(router.part_prompts)
        for marker in ("START-MARKER", "MIDDLE-MARKER", "END-MARKER"):
            self.assertIn(marker, sent_to_ai)                     # the AI saw every part
        self.assertIn("NOTES-1", router.final_prompt)               # and its notes reach the final request
        self.assertIn("NOTES-2", router.final_prompt)
        self.assertNotIn("middle omitted", router.final_prompt)    # nothing was skipped

    def test_writer_reads_every_part_of_a_long_readme(self):
        router = Router()
        self.run_with(router, generate_readme, dict(REPO, readme=make_readme(14000)))
        self.assertEqual(len(router.part_prompts), 3)
        self.assertEqual(len(router.prompts), 4)                   # 3 parts + the real request
        self.assert_every_part_read(router)

    def test_review_reads_every_part_of_a_long_readme(self):
        router = Router()
        self.run_with(router, analyze_readme, make_readme(30000))
        self.assert_every_part_read(router)

    def test_code_files_still_reach_the_final_request(self):
        router = Router()
        self.run_with(router, generate_readme, dict(REPO, readme=make_readme(14000)))
        self.assertIn("code_marker", router.final_prompt)


class HonestLimits(Base):
    def test_a_failure_while_reading_is_reported_not_hidden(self):
        router = Router(notes_status=429)
        with self.assertRaises(AIServiceError) as ctx:
            self.run_with(router, generate_readme, dict(REPO, readme=make_readme(14000)), raise_errors=True)
        self.assertIn("busy", str(ctx.exception))

    def test_review_still_returns_the_score_if_reading_fails(self):
        router = Router(notes_status=429)
        report = self.run_with(router, analyze_readme, make_readme(30000))
        self.assertTrue(report.startswith("SCORE:"))
        self.assertIn("AI commentary is unavailable", report)

    def test_absurdly_long_readme_falls_back_to_start_and_end(self):
        router = Router()
        self.run_with(router, generate_readme, dict(REPO, readme=make_readme(60000)))
        self.assertEqual(router.part_prompts, [])
        self.assertIn("middle omitted", router.final_prompt)
        self.assertIn("START-MARKER", router.final_prompt)
        self.assertIn("END-MARKER", router.final_prompt)


if __name__ == "__main__":
    unittest.main()