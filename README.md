# README Doctor 🩺  
[![README Health Check](https://github.com/Mohith417/readme-doctor/actions/workflows/readme-check.yml/badge.svg)](https://github.com/Mohith417/readme-doctor/actions/workflows/readme-check.yml)  
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)  
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## What is README Doctor?

**README Doctor** is a lightweight, AI‑powered CLI tool that inspects any GitHub repository’s `README.md`, evaluates its quality, and returns a **health score** together with concrete, actionable suggestions. When needed, it can even generate an improved version of the README automatically.

---

## Why does this matter?

A well‑written README is the front door of an open‑source project. Unfortunately, many repositories ship with sparse, outdated, or confusing documentation, which hurts discoverability and contributor onboarding. README Doctor helps you:

* Identify missing sections (installation, usage, contribution guidelines, etc.)  
* Detect unclear language, broken links, and formatting issues  
* Quantify overall README quality with a single score  
* Produce a polished, AI‑enhanced rewrite in seconds  

---

## Features

- **Health scoring** – a numeric score (0‑100) reflecting completeness, clarity, and best‑practice compliance.  
- **Issue detection** – pinpoint missing headings, dead links, bad markdown, and other common pitfalls.  
- **Auto‑generation** – with `--generate` the tool returns an AI‑crafted improved README.  
- **Score‑only mode** – `--score-only` returns just the numeric score for CI pipelines.  
- **GitHub token support** – pass a personal access token via `--token` to avoid rate‑limits.  
- **Batch processing** – analyse multiple repositories in one command.  

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Python** | 3.10 or newer |
| **Git** | Required only for fetching remote READMEs (handled internally) |
| **OpenAI API key** *(optional)* | Needed for the AI‑generated rewrite (`--generate`). Set `OPENAI_API_KEY` in your environment. |

---

## Installation

```bash
# Clone the repository
git clone https://github.com/Mohith417/readme-doctor.git
cd readme-doctor

# Install the required Python packages
pip install -r requirements.txt

# Install the package locally (adds the `readme-doctor` command)
pip install .
```

> The `setup.py` file registers a console script named **readme-doctor**, so after the last step you can run the tool from any terminal.

---

## Usage

### Basic health check

```bash
readme-doctor https://github.com/owner/repo
```

### Get only the numeric score (useful for CI)

```bash
readme-doctor https://github.com/owner/repo --score-only
```

### Generate an improved README

```bash
readme-doctor https://github.com/owner/repo --generate
```

### Use a personal GitHub token (avoids unauthenticated rate limits)

```bash
readme-doctor https://github.com/owner/repo --token YOUR_GITHUB_TOKEN
```

### Analyze several repositories at once

```bash
readme-doctor https://github.com/owner/repo1 https://github.com/owner/repo2 https://github.com/owner/repo3
```

#### Sample output

```
Repository: owner/repo
Health Score: 68/100
Issues:
  • Missing Installation section
  • 2 broken links
  • Bad markdown table formatting
Suggested improvements:
  • Add an Installation block with pip/conda instructions
  • Replace dead links with current documentation URLs
  • Reformat the feature table using proper markdown syntax
```

When `--generate` is used, the tool prints a full, AI‑crafted `README.md` that you can redirect to a file:

```bash
readme-doctor https://github.com/owner/repo --generate > NEW_README.md
```

---

## Development & Testing

The repository includes a GitHub Actions workflow (`.github/workflows/readme-check.yml`) that runs linting and basic unit tests on every push. To run the checks locally:

```bash
# Install test dependencies (already covered by requirements.txt)
pip install -r requirements.txt

# Execute the test suite
python -m unittest discover -s tests
```

*(If the `tests/` directory is added in the future; currently the CI ensures import sanity.)*

---

## Contributing

Contributions are welcome! Please follow these steps:

1. **Fork** the repository and create a new branch for your feature or bug‑fix.  
2. **Write tests** for any new functionality.  
3. Ensure the code passes the existing CI checks (`flake8`, `black`, etc.).  
4. Submit a **Pull Request** with a clear description of the change.  

For major changes, open an issue first to discuss the proposed design.

---

## License

This project is licensed under the **MIT License**. See the [LICENSE](https://github.com/Mohith417/readme-doctor/blob/main/LICENSE) file for details.
