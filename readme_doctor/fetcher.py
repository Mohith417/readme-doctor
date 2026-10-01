import base64
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlparse

import requests

# --- Reading a repo: files are read IN FULL (no excerpts). ---
MAX_FILES_TOTAL = 80           # read at most this many files (best files first)
MAX_FILE_BYTES = 500_000       # skip single files bigger than this (usually generated or data files)
MAX_TOTAL_BYTES = 6_000_000    # stop adding files once this much would be downloaded in total
OUTLINE_FILE_CHARS = 400       # size of the outline used for a file that does not fit
REQUEST_TIMEOUT = 20

# --- Fitting into the AI's size limit (only done when building the prompt) ---
# Groq free tier allows ~8000 tokens per minute for openai/gpt-oss-120b.
# On a paid plan set GROQ_TPM_LIMIT=250000 in .env and more of the repo is sent automatically.
DEFAULT_GROQ_TPM = 8000
CHARS_PER_TOKEN = 3

CODE_EXTENSIONS = (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs",
                   ".cpp", ".c", ".cs", ".rb", ".php", ".kt", ".swift")
MANIFEST_NAMES = {"requirements.txt", "setup.py", "pyproject.toml", "package.json", "pom.xml",
                  "build.gradle", "cargo.toml", "go.mod", "gemfile", "composer.json",
                  "dockerfile", "docker-compose.yml", ".env.example"}
ENTRY_NAMES = {"main.py", "app.py", "cli.py", "__main__.py", "manage.py", "server.py",
               "index.js", "server.js", "app.js", "main.js", "index.ts", "main.ts",
               "main.go", "main.rs", "lib.rs", "main.java", "app.java", "program.cs"}
SKIP_DIRS = {"node_modules", "venv", ".venv", "__pycache__", "dist", "build", "vendor", ".git",
             "site-packages", "target", ".next", "coverage", "migrations"}
LOW_VALUE_DIRS = {"test", "tests", "spec", "specs", "example", "examples", "docs", "doc",
                  "demo", "samples", "scripts", "benchmark", "benchmarks", "fixtures"}
OUTLINE_PREFIXES = ("def ", "async def ", "class ", "function ", "export ", "func ", "fn ",
                    "pub fn ", "pub struct ", "struct ", "impl ", "interface ", "public ",
                    "private ", "protected ", "@app.", "@router.", "@click.",
                    "app.get(", "app.post(", "app.use(", "router.get(", "router.post(")


class RepoFetchError(Exception):
    """Raised when a repo can't be fetched (only if raise_errors=True)."""


def parse_repo_url(repo_url):
    """Return (owner, repo). Accepts a trailing slash, .git, and /tree/... links."""
    url = repo_url.strip()
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.netloc.lower() not in ("github.com", "www.github.com"):
        raise RepoFetchError("That doesn't look like a GitHub URL. Use https://github.com/owner/repo")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise RepoFetchError("The URL needs an owner and a repo name, like https://github.com/owner/repo")
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def explain_status(status):
    if status == 404:
        return "Repo not found. Check the URL, or add a GitHub token if the repo is private."
    if status == 401:
        return "GitHub rejected the token. Check that it is correct and has not expired."
    if status == 403:
        return "GitHub refused the request. You may have hit the rate limit. Add a GitHub token and try again."
    return f"GitHub returned status {status}."


def _fail(message, raise_errors):
    if raise_errors:
        raise RepoFetchError(message)
    print(f"Error: {message}")
    return None


UNREACHABLE = "Could not reach GitHub. Check your internet connection and try again."


def is_candidate(path):
    segments = path.split("/")
    if any(seg.lower() in SKIP_DIRS for seg in segments[:-1]):
        return False
    name = segments[-1].lower()
    return name in MANIFEST_NAMES or name.endswith(CODE_EXTENSIONS)


def file_priority(path, size=0):
    """Smaller sorts first: root config files, entry points, source code, then tests/examples/docs."""
    segments = path.lower().split("/")
    name, dirs = segments[-1], segments[:-1]
    depth = len(dirs)
    low_value = (any(d in LOW_VALUE_DIRS for d in dirs) or name.startswith("test_")
                 or ".test." in name or ".spec." in name or name.endswith("_test.go")
                 or name == "conftest.py")
    if name in MANIFEST_NAMES:
        rank = 0 if depth == 0 else 3
    elif low_value:
        rank = 6
    elif name in ENTRY_NAMES:
        rank = 1
    else:
        rank = 2
    return (rank, depth, -size, path)


def select_files(file_entries):
    """file_entries: list of (path, size). Returns paths, best first, within the file-count and total-size limits."""
    candidates = [(p, s) for p, s in file_entries
                  if is_candidate(p) and not (s and s > MAX_FILE_BYTES)]
    candidates.sort(key=lambda ps: file_priority(ps[0], ps[1]))
    selected, total = [], 0
    for path, size in candidates:
        if len(selected) >= MAX_FILES_TOTAL:
            break
        if total + size > MAX_TOTAL_BYTES:
            continue
        selected.append(path)
        total += size
    return selected


def make_outline(text, max_chars):
    """Keep only definition lines (functions, classes, routes) so many files fit in little space."""
    lines, used = [], 0
    for line in text.splitlines():
        if line.lstrip().startswith(OUTLINE_PREFIXES):
            line = line.rstrip()[:120]
            if used + len(line) + 1 > max_chars:
                break
            lines.append(line)
            used += len(line) + 1
    return "\n".join(lines)


def _fetch_file_text(owner, repo, path, headers):
    # raw.githubusercontent.com does not use up the GitHub API rate limit
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{quote(path)}"
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    return response.content.decode("utf-8", errors="replace")


def read_repo_files(owner, repo, file_entries, headers):
    """Return {path: full text} for the most important files, best first."""
    selected = select_files(file_entries)
    if not selected:
        return {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        texts = list(pool.map(lambda p: _fetch_file_text(owner, repo, p, headers), selected))
    return {path: text for path, text in zip(selected, texts) if text and text.strip()}


def groq_tpm_limit():
    try:
        return max(2000, int(os.getenv("GROQ_TPM_LIMIT", DEFAULT_GROQ_TPM)))
    except ValueError:
        return DEFAULT_GROQ_TPM


def input_budget_chars(reserve_tokens):
    """Characters we can send, after reserving tokens for instructions and the AI's answer."""
    return max(3000, (groq_tpm_limit() - reserve_tokens) * CHARS_PER_TOKEN)


def pack_context(code_samples, budget_chars):
    """Fit files into budget_chars, best files first. Whole files when they fit, an outline when
    they don't, skipped only when there is no room at all. Returns (text, stats)."""
    parts, used = [], 0
    stats = {"full": 0, "outline": 0, "skipped": 0}
    for path, text in code_samples.items():
        block = f"\n### {path}\n```\n{text}\n```\n"
        if used + len(block) <= budget_chars:
            parts.append(block)
            used += len(block)
            stats["full"] += 1
            continue
        room = budget_chars - used - len(path) - 40
        outline = make_outline(text, min(OUTLINE_FILE_CHARS, room)) if room > 80 else ""
        if outline:
            block = f"\n### {path} (outline only)\n```\n{outline}\n```\n"
            parts.append(block)
            used += len(block)
            stats["outline"] += 1
        else:
            stats["skipped"] += 1
    return "".join(parts), stats


def fetch_repo_data(repo_url, github_token=None, raise_errors=False):
    # raise_errors=False (CLI): print the error and return None, as before.
    # raise_errors=True (web app): raise RepoFetchError with a readable message.
    try:
        owner, repo = parse_repo_url(repo_url)
    except RepoFetchError as e:
        return _fail(str(e), raise_errors)

    api_base = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    try:
        repo_response = requests.get(api_base, headers=headers, timeout=REQUEST_TIMEOUT)
        if repo_response.status_code != 200:
            return _fail(explain_status(repo_response.status_code), raise_errors)
        repo_data = repo_response.json()

        readme_content = "No README found"
        readme_response = requests.get(f"{api_base}/readme", headers=headers, timeout=REQUEST_TIMEOUT)
        if readme_response.status_code == 200:
            encoded = readme_response.json().get("content", "")
            readme_content = base64.b64decode(encoded).decode("utf-8", errors="replace")

        file_entries = []
        tree_response = requests.get(f"{api_base}/git/trees/HEAD?recursive=1",
                                     headers=headers, timeout=REQUEST_TIMEOUT)
        if tree_response.status_code == 200:
            for item in tree_response.json().get("tree", []):
                if item.get("type") == "blob":
                    file_entries.append((item["path"], item.get("size", 0)))
    except requests.RequestException:
        return _fail(UNREACHABLE, raise_errors)

    code_samples = read_repo_files(owner, repo, file_entries, headers)
    file_structure = [p for p, _ in file_entries]

    return {
        "name": repo_data.get("name"),
        "owner": repo_data.get("owner", {}).get("login", "unknown"),
        "description": repo_data.get("description"),
        "stars": repo_data.get("stargazers_count"),
        "language": repo_data.get("language"),
        "readme": readme_content,
        "file_structure": file_structure,
        "code_samples": code_samples,
    }