import os
import time

import requests
from dotenv import load_dotenv

from readme_doctor.fetcher import input_budget_chars, pack_context
from readme_doctor.rubric import evaluate_readme
from readme_doctor.rubric import issues as rubric_issues
from readme_doctor.rubric import suggestions as rubric_suggestions

load_dotenv()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
REQUEST_TIMEOUT = 90
MAX_ATTEMPTS = 3
MAX_WAIT_SECONDS = 20

ANALYSIS_RESERVE_TOKENS = 2500      # room kept for instructions + the AI's answer
ANALYSIS_OVERHEAD_CHARS = 2200
GENERATION_RESERVE_TOKENS = 4500
GENERATION_OVERHEAD_CHARS = 3000
CONDENSE_CHUNK_CHARS = 6000         # size of each piece when a README is too long for one request
MAX_CONDENSE_CALLS = 6              # READMEs up to ~36,000 characters are read completely
MIN_CODE_CHARS = 1500               # room always kept for source files

MESSAGES = {
    "no_key": "The AI key (GROQ_API_KEY) is not set.",
    "bad_key": "The AI key was rejected. Check that GROQ_API_KEY is correct.",
    "rate_limit": "The AI service is busy (free-plan limit reached). Wait a minute and try again.",
    "too_large": "This repo is too large for the AI's size limit, even after trimming.",
    "network": "Could not reach the AI service. Check the connection and try again.",
    "empty": "The AI returned an empty answer. Try again.",
    "server": "The AI service had a problem on its side. Try again in a moment.",
    "other": "The AI service returned an error.",
}


class _PrepError(Exception):
    """Reading the README in pieces failed (the AI was busy, down, ...)."""
    def __init__(self, kind, detail):
        super().__init__(detail)
        self.kind, self.detail = kind, detail


class AIServiceError(Exception):
    """Raised (only when raise_errors=True) with a message that is safe to show to a visitor."""


def _wait_seconds(response):
    try:
        wait = float(response.headers.get("retry-after", 10))
    except (TypeError, ValueError):
        wait = 10
    return max(1, min(wait, MAX_WAIT_SECONDS))


def _post_groq(prompt, temperature):
    """Return (text, error_kind, detail). error_kind is None on success."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None, "no_key", "GROQ_API_KEY not found in .env file"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    last_kind, last_detail = "other", ""
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requests.post(GROQ_URL, headers=headers, json=body, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            return None, "network", str(exc)

        status = response.status_code
        if status == 200:
            try:
                content = response.json()["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError):
                content = None
            if content and content.strip():
                return content, None, ""
            return None, "empty", "the AI returned an empty reply"

        detail = f"{status} - {response.text[:300]}"
        lowered = response.text.lower()
        if status == 401:
            return None, "bad_key", detail
        if status == 413 or (status == 429 and "request too large" in lowered):
            return None, "too_large", detail
        if status == 429:
            last_kind, last_detail = "rate_limit", detail
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(_wait_seconds(response))
            continue
        if status >= 500:
            last_kind, last_detail = "server", detail
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(2)
            continue
        return None, "other", detail
    return None, last_kind, last_detail


def call_groq(prompt, temperature=0.2):
    """Simple version kept for compatibility: returns the text, or None after printing the error."""
    text, kind, detail = _post_groq(prompt, temperature)
    if kind:
        print(f"Error: {detail or MESSAGES[kind]}")
    return text


def _ask_ai(build_prompt, temperature):
    """build_prompt(scale) -> prompt. If the AI says the request is too large, retry with less content."""
    text, kind, detail = None, "other", ""
    for scale in (1.0, 0.6, 0.35):
        try:
            prompt = build_prompt(scale)
        except _PrepError as exc:
            return None, exc.kind, exc.detail
        text, kind, detail = _post_groq(prompt, temperature)
        if kind != "too_large":
            break
    return text, kind, detail


def _fit_text(text, limit):
    """Return (text, was_cut). Keeps the start and the end when the text is too long."""
    limit = max(500, limit)
    if len(text) <= limit:
        return text, False
    head = int(limit * 0.7)
    tail = limit - head
    return (text[:head] + "\n\n[... middle omitted to fit the AI's size limit ...]\n\n" + text[-tail:]), True


def _split_chunks(text, size):
    """Cut text into consecutive pieces of at most `size` characters, at line breaks where possible."""
    chunks, current, length = [], [], 0
    for line in text.splitlines(keepends=True):
        while len(line) > size:                      # one enormous line
            if current:
                chunks.append("".join(current))
                current, length = [], 0
            chunks.append(line[:size])
            line = line[size:]
        if length + len(line) > size and current:
            chunks.append("".join(current))
            current, length = [], 0
        current.append(line)
        length += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def _condense(text, limit):
    """Make the AI read ALL of `text` piece by piece and return compact notes of at most `limit` characters.
    Returns (notes, error_kind, detail). Only absurdly long text (see MAX_CONDENSE_CALLS) falls back to start + end."""
    for _ in range(3):
        if len(text) <= limit:
            return text, None, ""
        chunks = _split_chunks(text, CONDENSE_CHUNK_CHARS)
        if len(chunks) > MAX_CONDENSE_CALLS:
            return _fit_text(text, limit)[0], None, ""
        notes = []
        for number, chunk in enumerate(chunks, 1):
            prompt = f"""
Rewrite part {number} of {len(chunks)} of a project's README as compact notes for a reviewer.
Keep EVERY fact: headings, commands, flags, versions, file names, URLs, requirements, warnings and examples (shortened).
Remove filler words and repetition. Aim for about 30% of the original length. Output only the notes.

README PART {number}/{len(chunks)}:
{chunk}
"""
            reply, kind, detail = _post_groq(prompt, 0)
            if kind:
                return None, kind, detail
            notes.append(reply.strip())
        text = "\n\n".join(notes)
    return (text if len(text) <= limit else _fit_text(text, limit)[0]), None, ""


def _prepare_readme(readme, limit, cache):
    """Return (text, label). The whole README if it fits, otherwise notes made from ALL of it."""
    if len(readme) <= limit:
        return readme, "README CONTENT"
    if "notes" not in cache:
        cache["notes"] = _condense(readme, limit)
    notes, kind, detail = cache["notes"]
    if kind:
        raise _PrepError(kind, detail)
    if len(notes) > limit:
        notes = _fit_text(notes, limit)[0]
    return notes, "README CONTENT (too long for one request, so the AI first read every part and wrote these notes)"


def _strip_fence(text):
    """Remove a ```markdown ... ``` wrapper if the AI added one around the whole answer."""
    lines = text.strip().splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text.strip()


def _format_report(score, summary, issues, suggestions):
    lines = [f"SCORE: {score}", f"SUMMARY: {' '.join(summary.split())}", "ISSUES:"]
    lines += [f"- {i}" for i in issues]
    lines += ["SUGGESTIONS:"] + [f"- {s}" for s in suggestions]
    return "\n".join(lines)


def _parse_ai_sections(text):
    parts = {"summary": "", "problems": [], "suggestions": []}
    current = None
    for raw in text.splitlines():
        clean = raw.replace("*", "").strip()
        upper = clean.upper()
        if not clean:
            continue
        if upper.startswith("SUMMARY:"):
            current, parts["summary"] = "summary", clean[len("SUMMARY:"):].strip()
        elif upper.startswith("PROBLEMS:"):
            current = "problems"
        elif upper.startswith("SUGGESTIONS:"):
            current = "suggestions"
        elif current == "summary":
            parts["summary"] += " " + clean
        elif current in ("problems", "suggestions") and clean[0] in "-•":
            item = clean.lstrip("-• ").strip()
            if item and not item.lower().startswith(("none", "no problem", "n/a")):
                parts[current].append(item)
    return parts


def analyze_readme(readme_content, file_structure=None, code_samples=None):
    """Return a report in the SCORE / SUMMARY / ISSUES / SUGGESTIONS format.

    The score and the checklist issues come from code (same input -> same score).
    The AI only adds the summary, README-vs-code problems and extra suggestions; if it is
    unavailable the report is still returned, with a note in the summary.
    """
    file_structure = list(file_structure or [])
    result = evaluate_readme(readme_content, file_structure)
    score = result["score"]
    found_issues = rubric_issues(result)
    fixes = rubric_suggestions(result)[:5]

    if not result["has_readme"]:
        return _format_report(score, "This repository has no README, so there is nothing to review yet.",
                              found_issues, fixes)

    cache = {}

    def build_prompt(scale):
        budget = max(3000, int((input_budget_chars(ANALYSIS_RESERVE_TOKENS) - ANALYSIS_OVERHEAD_CHARS) * scale))
        structure = ("\n".join(file_structure[:80]) or "Not available")[:1500]
        readme_text, readme_label = _prepare_readme(
            readme_content, max(500, budget - len(structure) - MIN_CODE_CHARS), cache)
        code_text, _ = pack_context(code_samples or {}, max(0, budget - len(readme_text) - len(structure)))
        known = "\n".join(f"- {i}" for i in found_issues) or "None"
        return f"""
You are a senior software engineer reviewing a GitHub README.
A checklist has already measured the README's structure. Do NOT give a score.

Checklist problems already found:
{known}

{readme_label}:
{readme_text}

Files in the repository:
{structure}

Key source files:
{code_text or "Not available"}

Respond in EXACTLY this format and nothing else:
SUMMARY: [2-3 sentences on how useful this README is to a new reader]
PROBLEMS:
- [something the README says that is wrong or outdated compared with the files above; write "- none" if there is nothing]
SUGGESTIONS:
- [up to 3 specific improvements for THIS project, different from the checklist problems above]

Do not use markdown tables. Do not add other sections.
"""

    text, kind, detail = _ask_ai(build_prompt, temperature=0)
    if kind:
        print(f"Error: {detail or MESSAGES[kind]}")
        summary = (f"The checklist found {len(found_issues)} missing item(s). "
                   f"AI commentary is unavailable right now: {MESSAGES[kind]}")
        return _format_report(score, summary, found_issues, fixes)

    ai = _parse_ai_sections(text)
    summary = ai["summary"] or f"The checklist found {len(found_issues)} missing item(s)."
    return _format_report(score, summary, found_issues + ai["problems"], fixes + ai["suggestions"][:3])


def detect_project_info(file_structure, code_samples):
    """Detect real project info from actual files"""
    
    # Detect build system
    build_system = "unknown"
    build_file = ""
    if any("pom.xml" in f for f in file_structure):
        build_system = "maven"
        build_file = "pom.xml"
    elif any("build.gradle" in f for f in file_structure):
        build_system = "gradle"
        build_file = "build.gradle"
    elif any("package.json" in f for f in file_structure):
        build_system = "npm"
        build_file = "package.json"
    elif any("requirements.txt" in f for f in file_structure):
        build_system = "pip"
        build_file = "requirements.txt"
    elif any("Cargo.toml" in f for f in file_structure):
        build_system = "cargo"
        build_file = "Cargo.toml"

    # Detect main entry point
    main_file = ""
    for f in file_structure:
        if f.lower().endswith("main.java"):
            main_file = f
            break
        elif f == "main.py" or f.endswith("/main.py"):
            main_file = f
            break
        elif f == "index.js" or f.endswith("/index.js"):
            main_file = f
            break
        elif f == "app.py" or f.endswith("/app.py"):
            main_file = f
            break

    # Detect source directory
    src_dir = ""
    if any(f.startswith("src/") for f in file_structure):
        src_dir = "src"
    elif any(f.startswith("lib/") for f in file_structure):
        src_dir = "lib"
    elif any(f.startswith("app/") for f in file_structure):
        src_dir = "app"

    # Detect if there's a docker setup
    has_docker = any("Dockerfile" in f or "docker-compose" in f for f in file_structure)

    # Get main class name for Java
    main_class = ""
    if main_file:
        main_class = main_file.split("/")[-1].replace(".java", "")

    return {
        "build_system": build_system,
        "build_file": build_file,
        "main_file": main_file,
        "main_class": main_class,
        "src_dir": src_dir,
        "has_docker": has_docker
    }


def generate_readme(repo_data, raise_errors=False):
    """Write an improved README. raise_errors=True raises AIServiceError instead of printing."""
    file_structure = repo_data.get("file_structure") or []
    code_samples = repo_data.get("code_samples") or {}
    project_info = detect_project_info(file_structure, code_samples)
    old_readme = repo_data.get("readme") or ""
    name = repo_data.get("name") or "the project"
    url = f"https://github.com/{repo_data.get('owner', 'unknown')}/{name}"

    cache = {}

    def build_prompt(scale):
        budget = max(3000, int((input_budget_chars(GENERATION_RESERVE_TOKENS) - GENERATION_OVERHEAD_CHARS) * scale))
        structure = ("\n".join(file_structure[:100]) or "Not available")[:1200]
        readme_text, readme_label = _prepare_readme(
            old_readme, max(500, budget - len(structure) - MIN_CODE_CHARS), cache)
        code_text, _ = pack_context(code_samples, max(0, budget - len(readme_text) - len(structure)))
        return f"""
You are a technical writer. Generate a professional, complete GitHub README.md for the following project.

Project Details:
- Name: {name}
- Description: {repo_data.get('description') or 'No description given'}
- Language: {repo_data.get('language') or 'Unknown'}
- Stars: {repo_data.get('stars')}
- GitHub URL: {url}

DETECTED PROJECT STRUCTURE (use this for accurate commands):
- Build system: {project_info['build_system']}
- Build file: {project_info['build_file']}
- Main entry point: {project_info['main_file']}
- Main class: {project_info['main_class']}
- Source directory: {project_info['src_dir']}
- Has Docker: {project_info['has_docker']}

Actual File Structure:
{structure}

Source files from the repository (most important first):
{code_text or 'Not available'}

{readme_label} - it may be outdated or wrong; trust the source files over it:
{readme_text}

Previous analysis feedback to address in this version:
{repo_data.get('previous_feedback', 'None - this is the first attempt')}

STRICT RULES - you MUST follow these:
1. ONLY use commands that match the detected build system above
2. ONLY reference files that exist in the actual file structure above
3. ONLY use the real main class name detected above for run commands
4. Do NOT invent folder names, file names, or commands that don't exist
5. If build system is unknown, say "compile manually with javac/gcc/etc"
6. Use the real GitHub URL for the clone command
7. ONLY mention command-line flags, options, environment variables and URLs that appear in the source files above
8. Keep what is correct in the existing README (purpose, working badges, useful sections) and improve the rest

Generate a complete README.md that includes:
1. Project title and badges
2. Clear description and problem it solves
3. Features list based on actual code
4. Prerequisites
5. Installation with REAL commands only
6. Usage with REAL code snippets from actual files
7. Troubleshooting section with common errors and fixes
8. Contributing guidelines
9. License section

Write only the README content in markdown, nothing else.
"""

    text, kind, detail = _ask_ai(build_prompt, temperature=0.3)
    if kind:
        if raise_errors:
            raise AIServiceError(MESSAGES[kind])
        print(f"Error: {detail or MESSAGES[kind]}")
        return None
    return _strip_fence(text)