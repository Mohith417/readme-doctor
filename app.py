import os
import time
from collections import defaultdict

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from readme_doctor.fetcher import fetch_repo_data, RepoFetchError
from readme_doctor.analyzer import analyze_readme, generate_readme
from readme_doctor.scorer import parse_score, get_grade

load_dotenv()

app = Flask(__name__)

# --- Simple rate limit: protects the free Groq quota (8000 tokens/minute) ---
WINDOW_SECONDS = 60
MAX_REQUESTS = 5
_hits = defaultdict(list)


def client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr


def rate_limited():
    ip = client_ip()
    now = time.time()
    _hits[ip] = [t for t in _hits[ip] if now - t < WINDOW_SECONDS]
    if len(_hits[ip]) >= MAX_REQUESTS:
        return True
    _hits[ip].append(now)
    return False


def parse_report(text):
    """Split the AI report (SCORE / SUMMARY / ISSUES / SUGGESTIONS) into parts."""
    parts = {"summary": "", "issues": [], "suggestions": []}
    current = None
    for raw in text.splitlines():
        clean = raw.replace("*", "").strip()
        upper = clean.upper()
        if not clean:
            continue
        if upper.startswith("SCORE:"):
            current = None
        elif upper.startswith("SUMMARY:"):
            current = "summary"
            parts["summary"] = clean[len("SUMMARY:"):].strip()
        elif upper.startswith("ISSUES:"):
            current = "issues"
        elif upper.startswith("SUGGESTIONS:"):
            current = "suggestions"
        elif current == "summary":
            parts["summary"] += " " + clean
        elif current in ("issues", "suggestions") and clean[0] in "-•":
            parts[current].append(clean.lstrip("-• ").strip())
    return parts


def get_input():
    """Read and check the url/token sent by the browser. Returns (url, token, error)."""
    body = request.get_json(silent=True) or {}
    url = str(body.get("url") or "").strip()
    if not url or len(url) > 300:
        return None, None, "Enter a GitHub repo URL, like https://github.com/owner/repo."
    # Visitor's own token (for private repos) wins. Otherwise use the server's
    # public-only token if one is set. Never use the personal GITHUB_TOKEN here.
    token = str(body.get("token") or "").strip() or os.getenv("WEB_GITHUB_TOKEN")
    return url, token, None


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/api/analyze")
def api_analyze():
    if rate_limited():
        return jsonify(error="Too many requests. Wait a minute and try again."), 429
    url, token, error = get_input()
    if error:
        return jsonify(error=error), 400

    try:
        data = fetch_repo_data(url, token, raise_errors=True)
    except RepoFetchError as e:
        return jsonify(error=str(e)), 400
    except Exception:
        return jsonify(error="Could not reach GitHub. Try again in a moment."), 502

    analysis = analyze_readme(data["readme"])
    if analysis is None:
        return jsonify(error="The AI service did not respond. It may be busy. Try again in a minute."), 502

    score = parse_score(analysis)
    grade, grade_message = get_grade(score)
    report = parse_report(analysis)
    return jsonify(
        name=data["name"],
        description=data["description"],
        stars=data["stars"],
        language=data["language"],
        score=score,
        grade=grade,
        grade_message=grade_message,
        summary=report["summary"],
        issues=report["issues"],
        suggestions=report["suggestions"],
    )


@app.post("/api/generate")
def api_generate():
    if rate_limited():
        return jsonify(error="Too many requests. Wait a minute and try again."), 429
    url, token, error = get_input()
    if error:
        return jsonify(error=error), 400

    try:
        data = fetch_repo_data(url, token, raise_errors=True)
    except RepoFetchError as e:
        return jsonify(error=str(e)), 400
    except Exception:
        return jsonify(error="Could not reach GitHub. Try again in a moment."), 502

    # One generation pass only: the CLI loop waits 30s between tries, which a web request can't.
    readme = generate_readme(data)
    if readme is None:
        return jsonify(error="The AI service did not respond. It may be busy. Try again in a minute."), 502
    return jsonify(readme=readme, name=data["name"])


if __name__ == "__main__":
    app.run(debug=True)