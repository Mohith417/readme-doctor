import os
import requests
from dotenv import load_dotenv

load_dotenv()

def analyze_readme(readme_content):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("Error: GROQ_API_KEY not found in .env file")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

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

Respond in this exact format:
SCORE: (give a score out of 100)
SUMMARY: (2-3 sentence overall summary)
ISSUES:
- (list each specific issue found)
SUGGESTIONS:
- (list each specific improvement)
"""

    body = {
        "model": "openai/gpt-oss-20b",
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