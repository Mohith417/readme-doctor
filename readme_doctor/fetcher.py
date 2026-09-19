import requests

def fetch_repo_data(repo_url):
    # Extract owner and repo name from URL
    parts = repo_url.rstrip('/').split('/')
    owner = parts[-2]
    repo = parts[-1]

    api_base = f"https://api.github.com/repos/{owner}/{repo}"

    # Fetch repo info
    repo_response = requests.get(api_base)
    if repo_response.status_code != 200:
        print(f"Error: Could not fetch repo. Status code: {repo_response.status_code}")
        return None

    repo_data = repo_response.json()

    # Fetch README
    readme_response = requests.get(f"{api_base}/readme")
    if readme_response.status_code != 200:
        readme_content = "No README found"
    else:
        import base64
        readme_encoded = readme_response.json().get('content', '')
        readme_content = base64.b64decode(readme_encoded).decode('utf-8')

    return {
        "name": repo_data.get("name"),
        "description": repo_data.get("description"),
        "stars": repo_data.get("stargazers_count"),
        "language": repo_data.get("language"),
        "readme": readme_content
    }