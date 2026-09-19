# README Doctor 🩺

![README Health Check](https://github.com/Mohith417/readme-doctor/actions/workflows/readme-check.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

An AI-powered CLI tool that analyzes any GitHub repository's README and gives it a health score with specific, actionable improvement suggestions.

## Problem It Solves
90% of open source projects have poor READMEs. README Doctor fetches any GitHub repo, analyzes its README using AI, scores it out of 100, and tells you exactly what to fix.

## Features
- Fetches any public GitHub repository
- AI-powered README analysis using Groq LLM
- Scores README quality out of 100 (A-F grade)
- Specific issues and actionable suggestions
- Auto-generates an improved README with --generate flag
- GitHub Action for automated README checks on every push

## Prerequisites
- Python 3.10+
- Free Groq API key (https://console.groq.com)

## Installation
git clone https://github.com/Mohith417/readme-doctor.git
cd readme-doctor
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

## Setup
Create a .env file in the root folder:
GROQ_API_KEY=your_groq_api_key_here

## Usage

Analyze a README:
python -m readme_doctor.cli https://github.com/any-user/any-repo

Auto-generate an improved README:
python -m readme_doctor.cli https://github.com/any-user/any-repo --generate

## Example Output
Score: 70/100 | Grade: C | Average README, needs work

## Tech Stack
- Python 3.13
- Groq LLM API (free tier)
- GitHub REST API
- Click CLI framework

## License
MIT