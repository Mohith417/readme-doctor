"""Tries the kinds of input real visitors type against a RUNNING README Doctor server.
No AI is used by these checks. Usage:  python scripts/smoke_test.py [http://127.0.0.1:5000]"""
import os
import sys
import time

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/")
PAUSE = float(os.getenv("SMOKE_PAUSE", "13"))     # the server allows 5 requests a minute per visitor
URL = "https://github.com/pallets/click"

# (what the visitor did, JSON sent, expected status, words that must be in the message)
POST_CASES = [
    ("empty box", {"url": ""}, 400, "GitHub repo URL"),
    ("nothing sent", {}, 400, "GitHub repo URL"),
    ("random words", {"url": "hello world"}, 400, "GitHub URL"),
    ("not GitHub (GitLab link)", {"url": "https://gitlab.com/x/y"}, 400, "GitHub URL"),
    ("a profile, no repo name", {"url": "https://github.com/Mohith417"}, 400, "owner and a repo"),
    ("400 characters of text", {"url": "https://github.com/" + "a" * 400}, 400, "GitHub repo URL"),
    ("repo that does not exist", {"url": "https://github.com/Mohith417/this-repo-does-not-exist"}, 400, "not found"),
    ("same, with spaces and a trailing slash", {"url": "  https://github.com/Mohith417/this-repo-does-not-exist/  "}, 400, "not found"),
    ("same, typed without https://", {"url": "github.com/Mohith417/this-repo-does-not-exist"}, 400, "not found"),
    ("wrong GitHub token", {"url": URL, "token": "not-a-real-token"}, 400, "rejected the token"),
]


def check(label, response, status, words):
    try:
        message = response.json().get("error", "")
    except ValueError:
        message = f"(not JSON) {response.text[:80]}"
    ok = response.status_code == status and words.lower() in message.lower()
    print(f"{'PASS' if ok else 'FAIL'}  {label:<42} {response.status_code}  {message[:70]}")
    return ok


def main():
    results = []
    try:
        page = requests.get(BASE + "/", timeout=15)
        results.append(page.status_code == 200 and "README Doctor" in page.text)
        print(f"{'PASS' if results[-1] else 'FAIL'}  {'home page loads':<42} {page.status_code}")
        health = requests.get(BASE + "/health", timeout=15)
        results.append(health.status_code == 200)
        print(f"{'PASS' if results[-1] else 'FAIL'}  {'health check':<42} {health.status_code}")
        wrong = requests.get(BASE + "/api/analyze", timeout=15)
        results.append(check("opening /api/analyze in the browser", wrong, 405, ""))
        missing = requests.get(BASE + "/no-such-page", timeout=15)
        results.append(missing.status_code == 404)
        print(f"{'PASS' if results[-1] else 'FAIL'}  {'unknown page gives 404':<42} {missing.status_code}")
    except requests.RequestException as exc:
        print(f"Could not reach {BASE}. Is the server running (python app.py)?  {exc}")
        sys.exit(2)

    print(f"\nSending {len(POST_CASES)} odd inputs, {PAUSE:.0f}s apart (the server limits each visitor to 5 a minute)...\n")
    for label, payload, status, words in POST_CASES:
        results.append(check(label, requests.post(BASE + "/api/analyze", json=payload, timeout=60), status, words))
        time.sleep(PAUSE)

    print("\nSending 8 requests as fast as possible (the limit should kick in)...")
    codes = [requests.post(BASE + "/api/analyze", json={}, timeout=15).status_code for _ in range(8)]
    limited = 429 in codes
    results.append(limited)
    print(f"{'PASS' if limited else 'FAIL'}  {'too many requests are refused (429)':<42} {codes}")

    print(f"\n{sum(results)} of {len(results)} checks passed.")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()