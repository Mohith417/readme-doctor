import requests
import base64
from urllib.parse import urlparse


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

    # Fetch repo info
    repo_response = requests.get(api_base, headers=headers)
    if repo_response.status_code != 200:
        return _fail(explain_status(repo_response.status_code), raise_errors)

    repo_data = repo_response.json()

    # Fetch README
    readme_response = requests.get(f"{api_base}/readme", headers=headers)
    if readme_response.status_code != 200:
        readme_content = "No README found"
    else:
        readme_encoded = readme_response.json().get('content', '')
        readme_content = base64.b64decode(readme_encoded).decode('utf-8')

    # Fetch file structure
    tree_response = requests.get(f"{api_base}/git/trees/HEAD?recursive=1", headers=headers)
    file_structure = []
    if tree_response.status_code == 200:
        tree = tree_response.json().get('tree', [])
        for item in tree:
            if item['type'] == 'blob':
                file_structure.append(item['path'])

    # Fetch content of key files
    code_samples = {}
    important_files = [
        f for f in file_structure
        if f.endswith(('.py', '.js', '.ts', '.java', '.go', '.rs', '.cpp', '.c'))
        and not any(skip in f for skip in ['node_modules', 'venv', '__pycache__', 'dist', 'build'])
    ]

    # Only read first 5 code files to avoid rate limits
    for filepath in important_files[:5]:
        file_response = requests.get(f"{api_base}/contents/{filepath}", headers=headers)
        if file_response.status_code == 200:
            try:
                content = file_response.json().get('content', '')
                decoded = base64.b64decode(content).decode('utf-8')
                code_samples[filepath] = decoded[:500]  # first 500 chars only
            except:
                pass

    return {
        "name": repo_data.get("name"),
        "owner": repo_data.get("owner", {}).get("login", "unknown"),
        "description": repo_data.get("description"),
        "stars": repo_data.get("stargazers_count"),
        "language": repo_data.get("language"),
        "readme": readme_content,
        "file_structure": file_structure[:50],
        "code_samples": code_samples
    }