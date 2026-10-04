import os
import unittest
from unittest.mock import patch

from readme_doctor.analyzer import AIServiceError, analyze_readme, generate_readme

README = "# Demo\n\nSome words about the demo project. " * 8 + "\n\n## Installation\n```bash\npip install demo\n```\n"
REPO = {"name": "demo", "owner": "me", "description": "d", "language": "Python", "stars": 1,
        "readme": README, "file_structure": ["app.py"], "code_samples": {"app.py": "print(1)"}}
DAILY = "Rate limit reached for model on tokens per day (TPD): Limit 200000, Used 199900, Requested 5000."
MINUTE = "Rate limit reached for model on tokens per minute (TPM): Limit 8000, Used 7900, Requested 3000."


class FakeResp:
    def __init__(self, status, text, headers=None, content=None):
        self.status_code, self.text, self.headers, self._content = status, text, headers or {}, content

    def json(self):
        if self.status_code != 200:
            raise ValueError("not json")
        return {"choices": [{"message": {"content": self._content}}]}


class Calls:
    def __init__(self, *responses):
        self.responses, self.count = list(responses), 0

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.count += 1
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


class Limits(unittest.TestCase):
    def run_with(self, fake, func, *args, **kwargs):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k"}), \
             patch("readme_doctor.analyzer.requests.post", fake), \
             patch("readme_doctor.analyzer.time.sleep") as sleep:
            self.sleep = sleep
            return func(*args, **kwargs)

    def test_daily_limit_gives_its_own_message_and_does_not_retry(self):
        fake = Calls(FakeResp(429, DAILY, {"retry-after": "30"}))
        with self.assertRaises(AIServiceError) as ctx:
            self.run_with(fake, generate_readme, dict(REPO), raise_errors=True)
        self.assertIn("daily limit", str(ctx.exception))
        self.assertEqual(fake.count, 1)
        self.sleep.assert_not_called()

    def test_a_very_long_wait_time_also_means_the_daily_limit(self):
        fake = Calls(FakeResp(429, "rate limited", {"retry-after": "3600"}))
        with self.assertRaises(AIServiceError) as ctx:
            self.run_with(fake, generate_readme, dict(REPO), raise_errors=True)
        self.assertIn("daily limit", str(ctx.exception))
        self.assertEqual(fake.count, 1)

    def test_a_per_minute_limit_is_still_waited_out_and_retried(self):
        fake = Calls(FakeResp(429, MINUTE, {"retry-after": "7"}), FakeResp(200, "ok", content="# New"))
        self.assertEqual(self.run_with(fake, generate_readme, dict(REPO)), "# New")
        self.assertEqual(fake.count, 2)
        self.sleep.assert_called_once_with(7.0)

    def test_review_still_returns_the_score_when_the_daily_limit_is_gone(self):
        fake = Calls(FakeResp(429, DAILY))
        report = self.run_with(fake, analyze_readme, README)
        self.assertTrue(report.startswith("SCORE:"))
        self.assertIn("daily limit", report)

    def test_the_technical_reason_is_written_to_the_server_log(self):
        fake = Calls(FakeResp(429, DAILY))
        with self.assertLogs("readme_doctor", level="WARNING") as logs:
            with self.assertRaises(AIServiceError):
                self.run_with(fake, generate_readme, dict(REPO), raise_errors=True)
        text = "\n".join(logs.output)
        self.assertIn("daily_limit", text)
        self.assertIn("tokens per day", text)


if __name__ == "__main__":
    unittest.main()