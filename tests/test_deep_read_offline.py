import itertools
import os
import unittest
from unittest.mock import patch

from readme_doctor import analyzer
from readme_doctor.analyzer import AIServiceError, describe_read_report, generate_readme


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
    """Fake Groq. Answers 'read these files' passes with numbered notes, the final request with a README."""
    def __init__(self, fail_notes=False, note_chars=30):
        self.prompts = []
        self.fail_notes = fail_notes
        self.note_chars = note_chars

    def __call__(self, url, headers=None, json=None, timeout=None):
        prompt = json["messages"][0]["content"]
        self.prompts.append(prompt)
        if "NEW FILES (pass" in prompt:
            if self.fail_notes:
                return FakeResp(429, text="rate limit")
            return FakeResp(200, f"NOTES-{len(self.passes)}" + "x" * self.note_chars)
        return FakeResp(200, "# New README")

    @property
    def passes(self):
        return [p for p in self.prompts if "NEW FILES (pass" in p]

    @property
    def final(self):
        return self.prompts[-1]


def repo(n_files, size=3000):
    files = {f"src/f{i}.py": f"# FILE-MARKER-{i}\n" + "def work():\n    pass\n" * (size // 20) for i in range(n_files)}
    return {"name": "demo", "owner": "me", "description": "d", "language": "Python", "stars": 1,
            "readme": "# Demo\n\nA small demo project.\n", "file_structure": list(files), "code_samples": files}


class Base(unittest.TestCase):
    def run_with(self, router, data, env=None, **kwargs):
        values = {"GROQ_API_KEY": "test-key"}
        values.update(env or {})
        with patch.dict(os.environ, values), \
             patch("readme_doctor.analyzer.requests.post", router), \
             patch("readme_doctor.analyzer.time.sleep"):
            return generate_readme(data, **kwargs)


class SmallOrPaid(Base):
    def test_small_repo_goes_in_word_for_word_with_no_extra_calls(self):
        router, data = Router(), repo(2, 1000)
        self.run_with(router, data)
        self.assertEqual(len(router.prompts), 1)
        self.assertIn("FILE-MARKER-0", router.final)
        self.assertIn("FILE-MARKER-1", router.final)
        self.assertEqual(data["read_report"]["mode"], "verbatim")
        self.assertEqual(describe_read_report(data["read_report"]), "The AI read all 2 source files in full.")

    def test_paid_plan_sends_a_big_repo_word_for_word_in_one_call(self):
        router, data = Router(), repo(12)
        self.run_with(router, data, env={"GROQ_TPM_LIMIT": "250000"})
        self.assertEqual(len(router.prompts), 1)
        for i in range(12):
            self.assertIn(f"FILE-MARKER-{i}", router.final)


class WholeRepoIsRead(Base):
    def test_every_file_reaches_the_ai_and_notes_reach_the_final_request(self):
        router, data = Router(), repo(12)                       # ~36,000 characters of code
        self.run_with(router, data)
        sent = "\n".join(router.passes)
        for i in range(12):
            self.assertIn(f"FILE-MARKER-{i}", sent)               # nothing skipped
        self.assertGreater(len(router.passes), 1)
        self.assertEqual(len(router.prompts), len(router.passes) + 1)
        self.assertIn(f"NOTES-{len(router.passes)}", router.final)   # the last pass's notes
        self.assertIn("after reading 12 source files completely", router.final)
        self.assertEqual(data["read_report"]["read_completely"], 12)

    def test_notes_roll_forward_from_one_pass_to_the_next(self):
        router = Router()
        self.run_with(router, repo(12))
        self.assertIn("(none yet)", router.passes[0])
        self.assertIn("NOTES-1", router.passes[1])

    def test_the_final_request_stays_small_whatever_the_ai_writes(self):
        router = Router(note_chars=20000)                         # an AI that writes far too much
        self.run_with(router, repo(12))
        self.assertLess(len(router.final), 20000)

    def test_a_huge_repo_is_limited_to_the_maximum_number_of_passes(self):
        router, data = Router(), repo(40)                         # ~120,000 characters
        self.run_with(router, data)
        self.assertEqual(len(router.passes), analyzer.MAX_DEEP_CALLS)
        report = data["read_report"]
        self.assertLess(report["read_completely"] + report["outline_only"] + report["skipped"], 41)
        self.assertGreater(report["outline_only"], 0)
        self.assertIn("(outline only)", router.final)
        self.assertIn("more were read as outlines", describe_read_report(report))

    def test_a_file_bigger_than_one_pass_is_read_in_parts_not_dropped(self):
        router, data = Router(), repo(1, 14000)                   # one 14,000-character file
        data["code_samples"]["src/f0.py"] += "# END-OF-FILE-MARKER\n"
        self.run_with(router, data)
        sent = "\n".join(router.passes)
        self.assertIn("FILE-MARKER-0", sent)
        self.assertIn("END-OF-FILE-MARKER", sent)
        self.assertIn("(part 2)", sent)
        self.assertEqual(data["read_report"]["read_completely"], 1)

    def test_a_second_attempt_reuses_the_reading_instead_of_repeating_it(self):
        router, data = Router(), repo(12)
        self.run_with(router, data)
        first = len(router.passes)
        self.run_with(router, data)
        self.assertEqual(len(router.passes), first)
        self.assertEqual(len(router.prompts), first + 2)          # only the final request was sent again

    def test_changed_files_are_read_again_not_taken_from_a_stale_reading(self):
        router, data = Router(), repo(12)
        self.run_with(router, data)
        first = len(router.passes)
        data["code_samples"] = repo(12, 4000)["code_samples"]
        self.run_with(router, data)
        self.assertGreater(len(router.passes), first)

    def test_progress_messages_are_reported(self):
        messages = []
        self.run_with(Router(), repo(12), progress=messages.append)
        self.assertTrue(messages)
        self.assertIn("pass 1 of", messages[0])


class Limits(Base):
    def test_a_failure_while_reading_is_reported_not_hidden(self):
        with self.assertRaises(AIServiceError) as ctx:
            self.run_with(Router(fail_notes=True), repo(12), raise_errors=True)
        self.assertIn("busy", str(ctx.exception))

    def test_time_limit_stops_early_and_says_so(self):
        router, data = Router(), repo(12)
        clock = itertools.count(0, 100)
        with patch.dict(os.environ, {"GROQ_API_KEY": "k"}), \
             patch("readme_doctor.analyzer.requests.post", router), \
             patch("readme_doctor.analyzer.time") as fake_time:
            fake_time.monotonic.side_effect = lambda: next(clock)
            result = generate_readme(data, time_limit=60)
        self.assertEqual(result, "# New README")
        self.assertEqual(len(router.passes), 1)
        self.assertTrue(data["read_report"]["stopped_early"])
        self.assertIn("stopped early", describe_read_report(data["read_report"]))

    def test_no_time_limit_means_every_pass_runs(self):
        router = Router()
        self.run_with(router, repo(12))
        self.assertGreater(len(router.passes), 1)

    def test_report_mentions_a_condensed_readme(self):
        text = describe_read_report({"files": 3, "mode": "verbatim", "full": 3, "outline": 0, "skipped": 0,
                                     "readme_condensed": True})
        self.assertIn("every part was read and condensed", text)

    def test_empty_report_gives_empty_text(self):
        self.assertEqual(describe_read_report(None), "")


if __name__ == "__main__":
    unittest.main()