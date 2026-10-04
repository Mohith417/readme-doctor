import os
import unittest
from unittest.mock import patch

from readme_doctor.analyzer import describe_read_report, generate_readme
from readme_doctor.factcheck import check_readme, describe_fact_check

PACKAGE_JSON = '{"name": "demo", "scripts": {"build": "x", "dev": "y"}, "dependencies": {"express": "1"}}'
REPO = {
    "name": "demo", "owner": "me", "description": "d", "language": "Python", "stars": 1,
    "readme": "# Old\n", "file_structure": ["app.py", "src/core.py", "LICENSE", "requirements.txt", "package.json", "docs/guide.md"],
    "code_samples": {
        "app.py": 'import click\n@click.option("--fast")\nKEY = os.getenv("DEMO_API_KEY")\n',
        "requirements.txt": "flask\nrequests\n",
        "package.json": PACKAGE_JSON,
    },
}


def claims(readme, repo=REPO):
    findings, checked = check_readme(readme, repo)
    return {(f.kind, f.claim) for f in findings}, checked


class Files(unittest.TestCase):
    def test_real_files_pass_and_missing_ones_are_flagged(self):
        found, _ = claims("See `app.py`, `src/core.py` and `core.py`. Also `src/missing.py`.")
        self.assertEqual(found, {("file", "src/missing.py")})

    def test_placeholders_and_runtime_files_are_not_flagged(self):
        text = "Create `.env`, run `python your_script.py`, open `output_report.md`, see `venv/bin/x.py`, `path/to/file.py`."
        self.assertEqual(claims(text)[0], set())

    def test_relative_links_must_exist(self):
        found, _ = claims("[License](LICENSE) [Guide](docs/guide.md) [Bad](LICENSE.txt) [Web](https://x.com/a.md) [Top](#usage)")
        self.assertEqual(found, {("link", "LICENSE.txt")})

    def test_run_commands_need_a_real_script(self):
        text = "```bash\npython app.py\npython3 src/core.py\npython serve.py\npython -m pip install flask\n```"
        self.assertEqual(claims(text)[0], {("file", "serve.py")})


class Flags(unittest.TestCase):
    def test_flags_must_appear_in_the_code(self):
        found, _ = claims("```bash\npython app.py --fast\npython app.py --turbo --help\n```")
        self.assertEqual(found, {("flag", "--turbo")})

    def test_flags_of_other_tools_are_ignored(self):
        text = "```bash\npip install --upgrade flask\ngit clone --depth 1 https://github.com/me/demo.git\nnpm install --save express\n```"
        self.assertEqual(claims(text)[0], set())

    def test_inline_flags_are_checked(self):
        self.assertEqual(claims("Use `--fast` or `--warp`.")[0], {("flag", "--warp")})


class Settings(unittest.TestCase):
    def test_environment_variables_must_appear_in_the_code(self):
        found, _ = claims("Set `DEMO_API_KEY` and `DEMO_SECRET_TOKEN`. Also `PYTHONPATH`.")
        self.assertEqual(found, {("setting", "DEMO_SECRET_TOKEN")})


class Packages(unittest.TestCase):
    def test_python_packages_must_be_in_the_manifests(self):
        found, _ = claims("```bash\npip install flask requests==2.0\npip install fastapi\npip install -r requirements.txt\npip install .\n```")
        self.assertEqual(found, {("package", "fastapi")})

    def test_requirements_file_must_exist(self):
        self.assertEqual(claims("```bash\npip install -r dev-requirements.txt\n```")[0], {("file", "dev-requirements.txt")})

    def test_node_packages_and_scripts(self):
        text = "```bash\nnpm install express\nnpm install lodash\nnpm run build\nnpm run deploy\nnpm install -g typescript\n```"
        self.assertEqual(claims(text)[0], {("package", "lodash"), ("npm script", "deploy")})

    def test_the_repos_own_name_is_a_valid_package(self):
        self.assertEqual(claims("```bash\npip install demo\n```")[0], set())


class Urls(unittest.TestCase):
    def test_a_near_miss_of_the_repo_address_is_flagged(self):
        text = "git clone https://github.com/me/demo.git and https://github.com/me/demo-cli and https://github.com/other/thing"
        self.assertEqual(claims(text)[0], {("url", "github.com/me/demo-cli")})


class NothingToCheckAgainst(unittest.TestCase):
    def test_without_code_only_files_and_links_are_checked(self):
        repo = dict(REPO, code_samples={})
        found, _ = claims("Run `python app.py --turbo`, set `SOME_KEY`, `pip install ghost`, see `nope.py`.", repo)
        self.assertEqual(found, {("file", "nope.py")})

    def test_a_clean_readme_has_no_findings_and_counts_its_claims(self):
        found, checked = claims("Run `python app.py --fast` with `DEMO_API_KEY` set, see `src/core.py`.")
        self.assertEqual(found, set())
        self.assertGreaterEqual(checked, 4)

    def test_same_input_same_result(self):
        text = "`--turbo` `nope.py` `SOME_KEY`"
        self.assertEqual({tuple(f) for f in check_readme(text, REPO)[0]}, {tuple(f) for f in check_readme(text, REPO)[0]})


class Wording(unittest.TestCase):
    def test_sentences(self):
        self.assertEqual(describe_fact_check(None), "")
        self.assertEqual(describe_fact_check({"checked": 0, "unverified": []}), "")
        self.assertIn("all 5", describe_fact_check({"checked": 5, "unverified": []}))
        bad = describe_fact_check({"checked": 5, "unverified": [{"claim": "--turbo"}], "fixed": True})
        self.assertIn("1 of 5", bad)
        self.assertIn("--turbo", bad)
        self.assertIn("One correction pass was run.", bad)


class FakeResp:
    def __init__(self, content):
        self.status_code, self.headers, self.text, self._c = 200, {}, content, content

    def json(self):
        return {"choices": [{"message": {"content": self._c}}]}


class Writer:
    """Fake Groq that returns the given README versions in order (the last one repeats)."""
    def __init__(self, *versions):
        self.versions, self.prompts = list(versions), []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.prompts.append(json["messages"][0]["content"])
        return FakeResp(self.versions.pop(0) if len(self.versions) > 1 else self.versions[0])


BAD = "# Demo\n\nRun `python app.py --turbo`."
BETTER = "# Demo\n\nRun `python app.py --fast`."
WORSE = "# Demo\n\nRun `python app.py --turbo --warp`."


class InTheWriter(unittest.TestCase):
    def write(self, writer, data=None, **kwargs):
        data = data if data is not None else dict(REPO)
        with patch.dict(os.environ, {"GROQ_API_KEY": "k"}), \
             patch("readme_doctor.analyzer.requests.post", writer), \
             patch("readme_doctor.analyzer.time.sleep"):
            return generate_readme(data, **kwargs), data

    def test_an_unsupported_claim_triggers_one_correction_pass(self):
        writer = Writer(BAD, BETTER)
        text, data = self.write(writer)
        self.assertEqual(text, BETTER)
        self.assertEqual(len(writer.prompts), 2)
        self.assertIn("--turbo", writer.prompts[1])                   # the AI is told what was wrong
        self.assertNotIn("fact-check found", writer.prompts[0])
        report = data["read_report"]["fact_check"]
        self.assertEqual((report["unverified"], report["fixed"]), ([], True))
        self.assertIn("all", describe_read_report(data["read_report"]))

    def test_a_clean_readme_costs_no_extra_call(self):
        writer = Writer(BETTER)
        text, data = self.write(writer)
        self.assertEqual((text, len(writer.prompts)), (BETTER, 1))
        self.assertFalse(data["read_report"]["fact_check"]["fixed"])

    def test_it_never_loops_more_than_one_correction(self):
        writer = Writer(BAD)
        _, data = self.write(writer)
        self.assertEqual(len(writer.prompts), 2)
        self.assertEqual(len(data["read_report"]["fact_check"]["unverified"]), 1)
        self.assertIn("--turbo", describe_read_report(data["read_report"]))

    def test_the_better_supported_version_is_kept(self):
        text, data = self.write(Writer(BAD, WORSE))
        self.assertEqual(text, BAD)
        self.assertEqual(len(data["read_report"]["fact_check"]["unverified"]), 1)

    def test_a_failed_correction_keeps_the_first_version(self):
        calls = {"n": 0}

        def post(url, headers=None, json=None, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return FakeResp(BAD)
            resp = FakeResp("")
            resp.status_code, resp.text = 500, "down"
            return resp
        text, data = self.write(post)
        self.assertEqual(text, BAD)
        self.assertFalse(data["read_report"]["fact_check"]["fixed"])

    def test_no_correction_pass_after_the_time_limit(self):
        import itertools
        clock = itertools.count(0, 100)
        writer = Writer(BAD, BETTER)
        data = dict(REPO)
        with patch.dict(os.environ, {"GROQ_API_KEY": "k"}), \
             patch("readme_doctor.analyzer.requests.post", writer), \
             patch("readme_doctor.analyzer.time") as fake_time:
            fake_time.monotonic.side_effect = lambda: next(clock)
            text = generate_readme(data, time_limit=60)
        self.assertEqual((text, len(writer.prompts)), (BAD, 1))


if __name__ == "__main__":
    unittest.main()