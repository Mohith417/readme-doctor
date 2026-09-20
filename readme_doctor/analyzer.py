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
{readme_content[:3000]}

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


def generate_readme(repo_data):
    # Build file structure string
    file_structure = repo_data.get('file_structure', [])
    file_structure_str = '\n'.join(file_structure[:30]) if file_structure else 'Not available'

    # Build code samples string
    code_samples = repo_data.get('code_samples', {})
    code_samples_str = ""
    for filepath, content in code_samples.items():
        code_samples_str += f"\n### {filepath}\n```\n{content}\n```\n"

    prompt = f"""
You are a technical writer. Generate a professional, complete GitHub README.md for the following project.

Project Details:
- Name: {repo_data['name']}
- Description: {repo_data['description']}
- Language: {repo_data['language']}
- Stars: {repo_data['stars']}

Existing README (for context):
{repo_data['readme'][:1000]}

Actual File Structure:
{file_structure_str}

Code Samples from actual files:
{code_samples_str[:2000]}

Generate a complete, well-structured README.md based on the ACTUAL code and file structure above.
Include:
1. Project title and badges
2. Clear description and problem it solves (based on actual code)
3. Features list (based on actual code)
4. Prerequisites
5. Installation instructions
6. Usage examples with REAL code snippets from the actual files
7. Contributing guidelines
8. License section

Write only the README content in markdown, nothing else.
"""
    return call_groq(prompt)