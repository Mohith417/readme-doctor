import os
import requests
from dotenv import load_dotenv

load_dotenv()

def call_groq(prompt):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("Error: GROQ_API_KEY not found in .env file")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=body
    )

    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}")
        return None

    return response.json()["choices"][0]["message"]["content"]


def analyze_readme(readme_content):
    prompt = f"""
You are a senior software engineer reviewing a GitHub README file.
Analyze the following README and provide specific, actionable feedback.

Check for these things:
1. Does it have a clear project title and description?
2. Does it explain what problem it solves?
3. Does it have installation instructions?
4. Does it have usage examples?
5. Does it mention prerequisites/requirements?
6. Does it have a license section?
7. Does it have contribution guidelines?
8. Is the formatting clean and readable?

README CONTENT:
{readme_content[:20000]}

You MUST respond in this EXACT format, no exceptions:
SCORE: [number between 0-100]
SUMMARY: [2-3 sentences]
ISSUES:
- [issue 1]
- [issue 2]
SUGGESTIONS:
- [suggestion 1]
- [suggestion 2]

Do not use markdown tables. Do not add extra sections. Follow the format exactly.
"""
    return call_groq(prompt)


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


def generate_readme(repo_data):
    # Build file structure string
    file_structure = repo_data.get('file_structure', [])
    file_structure_str = '\n'.join(file_structure[:50]) if file_structure else 'Not available'

    # Build code samples string
    code_samples = repo_data.get('code_samples', {})
    code_samples_str = ""
    for filepath, content in code_samples.items():
        code_samples_str += f"\n### {filepath}\n```\n{content}\n```\n"

    # Detect real project info
    project_info = detect_project_info(file_structure, code_samples)

    prompt = f"""
You are a technical writer. Generate a professional, complete GitHub README.md for the following project.

Project Details:
- Name: {repo_data['name']}
- Description: {repo_data['description']}
- Language: {repo_data['language']}
- Stars: {repo_data['stars']}
- GitHub URL: https://github.com/{repo_data.get('owner', 'unknown')}/{repo_data['name']}

DETECTED PROJECT STRUCTURE (use this for accurate commands):
- Build system: {project_info['build_system']}
- Build file: {project_info['build_file']}
- Main entry point: {project_info['main_file']}
- Main class: {project_info['main_class']}
- Source directory: {project_info['src_dir']}
- Has Docker: {project_info['has_docker']}

Actual File Structure:
{file_structure_str}

Code Samples from actual files:
{code_samples_str[:3000]}

Existing README (for context):
{repo_data['readme'][:500]}

STRICT RULES - you MUST follow these:
1. ONLY use commands that match the detected build system above
2. ONLY reference files that exist in the actual file structure above
3. ONLY use the real main class name detected above for run commands
4. Do NOT invent folder names, file names, or commands that don't exist
5. If build system is unknown, say "compile manually with javac/gcc/etc"
6. Use the real GitHub URL for clone command

Generate a complete README.md that includes:
1. Project title and badges
2. Clear description and problem it solves
3. Features list based on actual code
4. Prerequisites
5. Installation with REAL commands only
6. Usage with REAL code snippets from actual files
7. Contributing guidelines
8. License section

Write only the README content in markdown, nothing else.
"""
    return call_groq(prompt)