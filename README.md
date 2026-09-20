# README Doctor 🩺  

[![README Health Check](https://github.com/Mohith417/readme-doctor/actions/workflows/readme-check.yml/badge.svg)](https://github.com/Mohith417/readme-doctor/actions/workflows/readme-check.yml)  
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)  
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## What is README Doctor?

**README Doctor** is a lightweight, AI‑powered command‑line tool that analyses any GitHub repository’s `README.md`.  
It returns a health **score**, highlights potential issues, and can **auto‑generate** an improved version of the README.

> **Why it matters** – A clear, well‑structured README is often the first impression of a project. README Doctor helps maintain that first impression automatically, saving time for developers and contributors.

---

## Features

- **AI‑driven analysis** – Parses the README with a language model to assess readability, completeness, and structure.  
- **Health scoring** – Produces a numeric score (0‑100) that reflects overall README quality.  
- **Issue detection** – Highlights missing sections, vague language, and other common problems.  
- **Auto‑generation** – Optionally creates an improved README based on the analysis.  
- **Batch mode** – Evaluate multiple repositories in a single command.  
- **GitHub token support** – Use a personal token to avoid rate‑limits on private or heavily‑used repositories.

The core logic lives in:

- `readme_doctor/analyzer.py` – interacts with the AI model and extracts issues.  
- `readme_doctor/scorer.py` – computes the health score.  
- `readme_doctor/fetcher.py` – fetches raw `README.md` content from a repository.  
- `readme_doctor/cli.py` – defines the `readme-doctor` command‑line interface.

---

## Prerequisites

| Requirement | Minimum version |
|-------------|-----------------|
| Python      | 3.10+           |
| pip         | latest          |
| GitHub personal access token* | — (optional, but recommended for private repos or high request volume) |

\* Create a token at <https://github.com/settings/tokens> with **repo** scope.

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Mohith417/readme-doctor.git
cd readme-doctor

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install the package (adds the `readme-doctor` CLI)
pip install .
```

*If you prefer an editable install for development:*  

```bash
pip install -e .
```

---

## Usage

The installed command is `readme-doctor`. Below are the supported invocations:

| Command | Description |
|---------|-------------|
| `readme-doctor <repo_url>` | Analyse the README of a single repository and display the health score plus identified issues. |
| `readme-doctor <repo_url> --generate` | Analyse **and** output an AI‑generated improved README. |
| `readme-doctor <repo_url> --score-only` | Show only the numeric health score (no issue list). |
| `readme-doctor <repo_url> --token YOUR_GITHUB_TOKEN` | Provide a token to avoid API rate limits. |
| `readme-doctor <url1> <url2> <url3>` | Batch‑process multiple repositories in one call. |

### Example: Basic analysis

```bash
readme-doctor https://github.com/pallets/flask
```

_Output (example)_

```
🩺 README Health Score: 78/100
Issues found:
  • No "Installation" section
  • License information missing
  • Badges could be added for CI status
```

### Example: Generate a better README

```bash
readme-doctor https://github.com/pallets/flask --generate
```

The command prints a full markdown document that can be saved as `README.md`.

### Example: Use a personal token

```bash
readme-doctor https://github.com/private/repo --token ghp_YourTokenHere
```

### Example: Score‑only mode

```bash
readme-doctor https://github.com/pallets/flask --score-only
```

### Example: Batch processing

```bash
readme-doctor https://github.com/pallets/flask https://github.com/psf/requests https://github.com/django/django
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Rate limit exceeded` | Too many unauthenticated requests to the GitHub API. | Supply a personal access token via `--token`. |
| `Repository not found` | Wrong URL or private repo without a token. | Verify the URL, and if the repo is private, add `--token`. |
| `ImportError: No module named 'openai'` | Missing optional AI dependency. | Ensure `requirements.txt` was installed, or manually run `pip install openai`. |
| `SSL certificate verify failed` | System missing CA certificates. | Install/update `certifi` (`pip install -U certifi`) or configure your environment’s SSL store. |
| `Permission denied` on install | Trying to install globally without admin rights. | Use a virtual environment (`python -m venv .venv && source .venv/bin/activate`) or install with `--user`. |

If you encounter a different issue, please open an **Issue** on GitHub with the error traceback and the repository URL you were analysing.

---

## Contributing

Contributions are welcome! Please follow these steps:

1. **Fork** the repository and create a new branch for your feature or bug‑fix.  
2. Ensure you have Python 3.10+ and the development dependencies installed:

   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

3. Run the test suite (if added in the future) and linting tools.  
4. Submit a **Pull Request** with a clear description of what you changed.  
5. Make sure your code adheres to the existing style and includes docstrings where appropriate.

For major changes, open an **Issue** first to discuss the proposed modification.

---

## License

This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.
