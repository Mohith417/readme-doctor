import requests
import base64

def fetch_repo_data(repo_url, github_token=None):
    # Extract owner and repo name from URL
    parts = repo_url.rstrip('/').split('/')
    owner = parts[-2]
    repo = parts[-1]

    api_base = f"https://api.github.com/repos/{owner}/{repo}"
    
    headers = {}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    # Fetch repo info
    repo_response = requests.get(api_base, headers=headers)
    if repo_response.status_code != 200:
        print(f"Error: Could not fetch repo. Status code: {repo_response.status_code}")
        return None

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