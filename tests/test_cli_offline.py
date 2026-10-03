import os
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from readme_doctor.cli import main

REPORT = "SCORE: 70\nSUMMARY: ok\nISSUES:\n- a\nSUGGESTIONS:\n- b\n"
DATA = {"name": "demo", "owner": "me", "description": "d", "stars": 1, "language": "Python",
        "readme": "# readme", "file_structure": ["LICENSE", "app.py"], "code_samples": {"app.py": "print(1)"}}


class CliWiring(unittest.TestCase):
    def test_single_repo_passes_the_readme_files_and_code(self):
        with patch("readme_doctor.cli.fetch_repo_data", return_value=dict(DATA)), \
             patch("readme_doctor.cli.analyze_readme", return_value=REPORT) as analyze:
            result = CliRunner().invoke(main, ["https://github.com/me/demo", "--score-only"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("70/100", result.output)
        analyze.assert_called_once_with("# readme", ["LICENSE", "app.py"], {"app.py": "print(1)"})

    def test_every_repo_in_a_multi_repo_run_passes_files_and_code(self):
        with patch("readme_doctor.cli.fetch_repo_data", return_value=dict(DATA)), \
             patch("readme_doctor.cli.analyze_readme", return_value=REPORT) as analyze:
            result = CliRunner().invoke(main, ["https://github.com/me/a", "https://github.com/me/b"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(analyze.call_count, 2)
        for call in analyze.call_args_list:
            self.assertEqual(call.args, ("# readme", ["LICENSE", "app.py"], {"app.py": "print(1)"}))

    def test_generate_saves_a_file_even_if_every_score_is_zero(self):
        zero = "SCORE: 0\nSUMMARY: x\nISSUES:\nSUGGESTIONS:\n"
        runner = CliRunner()
        with runner.isolated_filesystem(), \
             patch("readme_doctor.cli.fetch_repo_data", return_value=dict(DATA)), \
             patch("readme_doctor.cli.generate_readme", return_value="# New README"), \
             patch("readme_doctor.cli.analyze_readme", return_value=zero), \
             patch("readme_doctor.cli.time.sleep"):
            result = runner.invoke(main, ["https://github.com/me/demo", "--generate"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue(os.path.exists("demo_improved_README.md"))
            with open("demo_improved_README.md", encoding="utf-8") as f:
                self.assertEqual(f.read(), "# New README")


if __name__ == "__main__":
    unittest.main()