"""Checks a written README against the repo's own files. No AI is used, so the result is always the same."""
import json
import re
from collections import namedtuple

Finding = namedtuple("Finding", "kind claim why")

NOT_FOUND = "not found in the repo's files that were read"
PROMPT = re.compile(r"^(?:\(venv\)\s*)?(?:PS [^>]*>|[$>])\s*")
PATH_RE = re.compile(r"^[\w.\-/]+\.(?:py|js|ts|tsx|jsx|java|go|rs|rb|php|cs|cpp|c|h|json|ya?ml|toml|txt|md|cfg|ini|html|css|sh|bat|xml|gradle)$", re.I)
FLAG_RE = re.compile(r"(?<![\w-])(--[a-zA-Z][\w-]*)")
ENV_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
HTML_LINK_RE = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", re.I)
GITHUB_RE = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)")

THIRD_PARTY = {"pip", "pip3", "git", "npm", "npx", "yarn", "pnpm", "docker", "docker-compose", "curl", "wget",
               "brew", "apt", "apt-get", "conda", "cargo", "go", "mvn", "gradle", "poetry", "uv", "sudo", "cd",
               "echo", "mkdir", "cp", "mv", "rm", "export", "set", "source", "make", "choco", "winget"}
THIRD_PARTY_MODULES = {"pip", "venv", "http", "unittest", "pytest", "flask", "uvicorn", "gunicorn", "black", "build",
                       "ensurepip", "json", "http.server", "virtualenv", "twine"}
TOOLING = {"pip", "setuptools", "wheel", "virtualenv", "pipenv", "poetry", "uv", "build", "twine"}
COMMON_FLAGS = {"--help", "--version"}
COMMON_ENV = {"PYTHONPATH", "VIRTUAL_ENV", "NODE_ENV", "JAVA_HOME", "CLASSPATH", "PYTHONUNBUFFERED"}
PLACEHOLDERS = ("your", "example", "path/to", "my_", "my-", "foo", "bar", "xxx", "filename", "sample",
                "<", "{", "*", "$", "~")
RUNTIME_NAMES = ("output", "report", "result", "improved", ".log", "cache", "tmp", "temp", "backup")
RUNTIME_DIRS = {"venv", ".venv", "node_modules", "dist", "build", "__pycache__", "coverage", ".git"}
MANIFESTS = ("requirements", "pyproject.toml", "setup.py", "setup.cfg", "pipfile", "environment.yml")


def _lines(readme):
    """Return (code_lines, inline_spans, prose_lines)."""
    code, prose, in_code = [], [], False
    for line in readme.splitlines():
        if line.strip().startswith(("```", "~~~")):
            in_code = not in_code
            continue
        (code if in_code else prose).append(line)
    spans = [s.strip() for line in prose for s in re.findall(r"`([^`\n]+)`", line)]
    return code, spans, prose


def _exists(claim, paths, dirs, names):
    c = claim.strip()
    while c.startswith("./"):
        c = c[2:]
    c = c.rstrip("/")
    if not c or c in paths or c in dirs:
        return True
    if "/" not in c and c.lower() in names:
        return True
    return any(p.endswith("/" + c) for p in paths) or any(d.endswith("/" + c) for d in dirs)


def _is_placeholder_path(token):
    low = token.lower()
    segments = low.split("/")
    return (token.startswith(".") or any(p in low for p in PLACEHOLDERS) or any(r in low for r in RUNTIME_NAMES)
            or any(seg in RUNTIME_DIRS for seg in segments[:-1]))


def check_readme(readme, repo_data):
    """Return (findings, number_of_distinct_claims_checked)."""
    files = repo_data.get("file_structure") or []
    samples = repo_data.get("code_samples") or {}
    paths, dirs, names = set(files), set(), {f.split("/")[-1].lower() for f in files}
    for f in files:
        parts = f.split("/")
        dirs.update("/".join(parts[:i]) for i in range(1, len(parts)))
    code_text = "\n".join(samples.values()) + "\n" + "\n".join(files)
    manifest_text = "\n".join(t for p, t in samples.items() if p.lower().split("/")[-1].startswith(MANIFESTS)).lower().replace("_", "-")
    package_json = next((t for p, t in samples.items() if p.split("/")[-1] == "package.json"), "")
    owner, name = (repo_data.get("owner") or "").lower(), (repo_data.get("name") or "").lower()

    findings, seen = [], set()

    def claim(kind, value, ok, why=NOT_FOUND):
        if (kind, value) in seen:
            return
        seen.add((kind, value))
        if not ok:
            findings.append(Finding(kind, value, why))

    code_lines, spans, prose = _lines(readme)
    pseudo_lines = [PROMPT.sub("", line).strip() for line in code_lines] + spans
    have_code = bool(samples)

    # 1) file names written in `code`, and relative links
    for span in spans:
        if " " not in span and PATH_RE.match(span) and not _is_placeholder_path(span):
            claim("file", span, _exists(span, paths, dirs, names))
    for line in prose:
        for target in LINK_RE.findall(line) + HTML_LINK_RE.findall(line):
            target = target.split("#")[0].split("?")[0]
            if target and "://" not in target and not target.startswith(("mailto:", "tel:", "data:", "/")) \
                    and not _is_placeholder_path(target):
                claim("link", target, _exists(target, paths, dirs, names))

    # 2) commands, flags, packages
    for line in pseudo_lines:
        words = line.split()
        if not words:
            continue
        first = words[0].lower()
        runs_python = first in ("python", "python3", "py")
        module = words[2] if runs_python and len(words) > 2 and words[1] == "-m" else None
        third_party = first in THIRD_PARTY or (module is not None and module.split(".")[0] in THIRD_PARTY_MODULES)

        if runs_python and module is None and len(words) > 1 and PATH_RE.match(words[1]) and not _is_placeholder_path(words[1]):
            claim("file", words[1], _exists(words[1], paths, dirs, names))
        elif first in ("node", "bash", "sh") and len(words) > 1 and PATH_RE.match(words[1]) and not _is_placeholder_path(words[1]):
            claim("file", words[1], _exists(words[1], paths, dirs, names))
        elif first.startswith("./") and PATH_RE.match(first) and not _is_placeholder_path(first):
            claim("file", first, _exists(first, paths, dirs, names))

        if first in ("pip", "pip3") and len(words) > 1 and words[1] == "install" or \
                (runs_python and words[1:3] == ["-m", "pip"] and words[3:4] == ["install"]):
            rest = words[words.index("install") + 1:]
            skip_next = False
            for i, tok in enumerate(rest):
                if skip_next:
                    skip_next = False
                    continue
                if tok in ("-r", "--requirement") and i + 1 < len(rest):
                    claim("file", rest[i + 1], _exists(rest[i + 1], paths, dirs, names))
                    skip_next = True
                elif tok in ("-e", "--editable", "-c", "--constraint", "--index-url", "-i"):
                    skip_next = True
                elif tok.startswith("-") or tok in (".", "..") or any(c in tok for c in "/:@\\<>{}$"):
                    continue
                else:
                    pkg = re.split(r"[=<>!~;\[]", tok)[0].lower().replace("_", "-")
                    if pkg and pkg not in TOOLING and manifest_text:
                        ok = pkg in manifest_text or pkg == name.replace("_", "-")
                        claim("package", pkg, ok)
        if first in ("npm", "yarn", "pnpm") and len(words) > 1 and words[1] in ("install", "i", "add") \
                and "-g" not in words and "--global" not in words and package_json:
            for tok in words[2:]:
                if tok.startswith("-"):
                    continue
                pkg = ("@" + tok[1:].split("@")[0]) if tok.startswith("@") else tok.split("@")[0]
                if pkg:
                    claim("package", pkg, f'"{pkg.lower()}"' in package_json.lower())
        if first == "npm" and len(words) > 2 and words[1] == "run" and package_json:
            try:
                scripts = json.loads(package_json).get("scripts", {})
                claim("npm script", words[2], words[2] in scripts)
            except ValueError:
                pass

        if have_code and not third_party:
            for flag in FLAG_RE.findall(line):
                if flag not in COMMON_FLAGS:
                    claim("flag", flag, flag in code_text)

    # 3) environment variables
    if have_code:
        for line in pseudo_lines:
            for var in ENV_RE.findall(line):
                if var not in COMMON_ENV:
                    claim("setting", var, var in code_text)

    # 4) the repo's own GitHub address
    for gh_owner, gh_repo in GITHUB_RE.findall(readme):
        gh_repo = re.sub(r"\.git$", "", gh_repo).rstrip(".")
        if owner and name and (gh_owner.lower() == owner) != (gh_repo.lower() == name):
            if gh_owner.lower() == owner or gh_repo.lower() == name:
                claim("url", f"github.com/{gh_owner}/{gh_repo}", False,
                      f"does not match this repository ({repo_data.get('owner')}/{repo_data.get('name')})")
    return findings, len(seen)


def format_findings(findings):
    lines = [f"- {f.kind} `{f.claim}`: {f.why}" for f in findings[:10]]
    return ("A fact-check found these claims in the previous version that the repository's files do not support. "
            "Remove them, or replace them with facts taken from the source files:\n" + "\n".join(lines))


def describe_fact_check(report):
    """One plain sentence about the fact-check result ("" when there was nothing to check)."""
    if not report or not report.get("checked"):
        return ""
    bad, checked = report.get("unverified", []), report["checked"]
    fixed = " One correction pass was run." if report.get("fixed") else ""
    if not bad:
        return f"Fact-check: all {checked} file names, commands, flags and settings mentioned were found in the repo's files.{fixed}"
    shown = ", ".join(item["claim"] for item in bad[:5]) + (f" and {len(bad) - 5} more" if len(bad) > 5 else "")
    return f"Fact-check: {len(bad)} of {checked} items could not be found in the repo's files ({shown}). Please check them before publishing.{fixed}"