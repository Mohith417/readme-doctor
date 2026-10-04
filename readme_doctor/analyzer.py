import logging
import os
import time
from collections import Counter

import requests
from dotenv import load_dotenv

from readme_doctor.fetcher import input_budget_chars, pack_context
from readme_doctor.rubric import evaluate_readme
from readme_doctor.rubric import issues as rubric_issues
from readme_doctor.rubric import suggestions as rubric_suggestions

load_dotenv()

log = logging.getLogger("readme_doctor")

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
DEEP_BATCH_CHARS = 6000             # source files are read by the AI in pieces of this size
MAX_DEEP_CALLS = 8                  # up to ~48,000 characters of source are read completely

MESSAGES = {
    "no_key": "The AI key (GROQ_API_KEY) is not set.",
    "bad_key": "The AI key was rejected. Check that GROQ_API_KEY is correct.",
    "rate_limit": "The AI service is busy (free-plan limit reached). Wait a minute and try again.",
    "daily_limit": "The AI's free daily limit has been used up. It resets within about a day, so please try again later.",
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


def _is_daily_limit(response):
    """True when Groq says the DAILY quota is gone (waiting a minute will not help)."""
    text = response.text.lower()
    if "per day" in text or "(tpd)" in text or "(rpd)" in text:
        return True
    try:
        return float(response.headers.get("retry-after", 0)) > 120
    except (TypeError, ValueError):
        return False


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
        if status == 429 and _is_daily_limit(response):
            return None, "daily_limit", detail
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


def _batch_files(code_samples, size):
    """Lay the files (best first) end to end in batches of about `size` characters.
    A file that does not fit in the space left is continued in the next batch, so no space is wasted."""
    batches, current, length = [], [], 0
    for path, text in code_samples.items():
        part, rest = 0, text
        while rest:
            space = size - length
            if space < 200 and current:
                batches.append(current)
                current, length = [], 0
                space = size
            if len(rest) <= space:
                piece, rest = rest, ""
            else:
                cut = rest.rfind("\n", 0, space)
                cut = cut + 1 if cut > 0 else space
                piece, rest = rest[:cut], rest[cut:]
            part += 1
            label = path if (part == 1 and not rest) else f"{path} (part {part})"
            current.append((path, label, piece))
            length += len(piece)
    if current:
        batches.append(current)
    return batches


def _batch_text(batch):
    return "\n".join(f"### {label}\n```\n{piece}\n```" for _, label, piece in batch)


def _read_whole_repo(code_samples, budget, start, time_limit, progress):
    """Make the repo's source known to the AI within `budget` characters.
    Small repos go in word for word. Bigger ones are read by the AI in passes, keeping rolling notes.
    Returns (text, report, error_kind, detail)."""
    note = progress or (lambda message: None)
    total = sum(len(path) + len(text) + 20 for path, text in code_samples.items())
    if total <= budget:
        text, stats = pack_context(code_samples, budget)
        return text, {"files": len(code_samples), "mode": "verbatim", "ai_passes": 0, **stats}, None, ""

    all_batches = _batch_files(code_samples, DEEP_BATCH_CHARS)
    planned = all_batches[:MAX_DEEP_CALLS]
    cap = max(800, int(budget * 0.8))
    notes, done, stopped = "", 0, False
    for number, batch in enumerate(planned, 1):
        if time_limit is not None and number > 1 and time.monotonic() - start > time_limit:
            stopped = True
            break
        note(f"Reading the source files, pass {number} of {len(planned)}...")
        prompt = f"""
You are reading a software project's source files to collect facts for its README.

Notes so far (from the earlier files):
{notes or '(none yet)'}

NEW FILES (pass {number} of {len(planned)}):
{_batch_text(batch)}

Write the UPDATED notes covering the earlier notes AND the new files, in at most {cap} characters.
Keep exact names. Cover: what the project does, entry points, commands and flags, environment variables,
configuration, dependencies, routes or endpoints, how to run and test. Output only the notes.
"""
        reply, kind, detail = _post_groq(prompt, 0)
        if kind:
            return None, None, kind, detail
        notes = reply.strip()
        if len(notes) > cap:
            notes = _fit_text(notes, cap)[0]
        done += 1

    parts_read = Counter(path for batch in planned[:done] for path, _, _ in batch)
    parts_total = Counter(path for batch in all_batches for path, _, _ in batch)
    covered = {path for path in parts_read if parts_read[path] == parts_total[path]}   # read from start to end
    rest = {path: text for path, text in code_samples.items() if path not in covered}
    if rest:
        rest_text, stats = pack_context(rest, max(0, budget - len(notes) - 120))
    else:
        rest_text, stats = "", {"full": 0, "outline": 0, "skipped": 0}
    text = f"Notes written by the AI after reading {len(covered)} source files completely:\n{notes}\n{rest_text}"
    report = {"files": len(code_samples), "mode": "notes", "ai_passes": done,
              "read_completely": len(covered) + stats["full"], "outline_only": stats["outline"],
              "skipped": stats["skipped"], "stopped_early": stopped}
    return text, report, None, ""


def describe_read_report(report):
    """One plain sentence (or two) saying what the AI actually read."""
    if not report:
        return ""
    files = report.get("files", 0)
    if report.get("mode") == "verbatim":
        full, outline, skipped = report.get("full", 0), report.get("outline", 0), report.get("skipped", 0)
        if outline or skipped:
            text = (f"The AI read {full} of {files} source files in full, {outline} as outlines, "
                    f"and {skipped} not at all (size limit).")
        else:
            text = f"The AI read all {files} source files in full."
    else:
        text = (f"The AI read {report['read_completely']} of {files} source files completely, "
                f"in {report['ai_passes']} passes.")
        if report.get("outline_only"):
            text += f" {report['outline_only']} more were read as outlines."
        if report.get("skipped"):
            text += f" {report['skipped']} were not included (size limit)."
        if report.get("stopped_early"):
            text += " It stopped early to stay within the time limit; the command line tool does a complete read."
    if report.get("readme_condensed"):
        text += " The old README was too long for one request, so every part was read and condensed."
    return text


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


def generate_readme(repo_data, raise_errors=False, progress=None, time_limit=None):
    """Write an improved README. raise_errors=True raises AIServiceError instead of printing.
    progress(message) is called while the source files are being read. time_limit (seconds) makes the
    repo reading stop early (the web app uses this). What was read is stored in repo_data["read_report"]."""
    start = time.monotonic()
    file_structure = repo_data.get("file_structure") or []
    code_samples = repo_data.get("code_samples") or {}
    project_info = detect_project_info(file_structure, code_samples)
    old_readme = repo_data.get("readme") or ""
    name = repo_data.get("name") or "the project"
    url = f"https://github.com/{repo_data.get('owner', 'unknown')}/{name}"

    # Repeated attempts on the same repo share one reading; a different README or file set starts fresh.
    signature = (len(old_readme), tuple((path, len(text)) for path, text in code_samples.items()))
    cache = repo_data.get("_read_cache")
    if not cache or cache.get("signature") != signature:
        cache = {"signature": signature}
        repo_data["_read_cache"] = cache

    def build_prompt(scale):
        budget = max(3000, int((input_budget_chars(GENERATION_RESERVE_TOKENS) - GENERATION_OVERHEAD_CHARS) * scale))
        structure = ("\n".join(file_structure[:100]) or "Not available")[:1200]
        readme_text, readme_label = _prepare_readme(
            old_readme, max(500, budget - len(structure) - MIN_CODE_CHARS), cache)
        code_budget = max(0, budget - len(readme_text) - len(structure))
        if "repo" not in cache:
            cache["repo"] = _read_whole_repo(code_samples, code_budget, start, time_limit, progress)
        code_text, report, kind, detail = cache["repo"]
        if kind:
            raise _PrepError(kind, detail)
        if len(code_text) > code_budget:                 # only when retrying with a smaller budget
            code_text = _fit_text(code_text, code_budget)[0]
        cache["report"] = report
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

What the repository's source files contain (most important first):
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
        log.warning("AI request failed (%s): %s", kind, detail)     # the technical reason, for the server log
        if raise_errors:
            raise AIServiceError(MESSAGES[kind])
        print(f"Error: {detail or MESSAGES[kind]}")
        return None
    repo_data["read_report"] = dict(cache.get("report") or {}, readme_condensed="notes" in cache)
    return _strip_fence(text)