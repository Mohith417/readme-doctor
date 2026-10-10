"""Facts for the README's header and structure, built from the repo itself so nothing can be invented."""
import re

SKIP = {"node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".git", ".idea", ".vscode", "site-packages"}


def build_badges(repo_data):
    """Markdown badges that are true for this repo. Nothing is added unless the repo really has it."""
    owner, name = repo_data.get("owner"), repo_data.get("name")
    if not owner or not name or owner == "unknown":
        return []
    files = repo_data.get("file_structure") or []
    base = f"{owner}/{name}"
    badges = []
    for path in sorted(f for f in files if re.fullmatch(r"\.github/workflows/[\w.-]+\.ya?ml", f)):
        workflow = path.split("/")[-1]
        link = f"https://github.com/{base}/actions/workflows/{workflow}"
        badges.append(f"[![{re.sub(r'\.ya?ml$', '', workflow)}]({link}/badge.svg)]({link})")
    if any("/" not in f and re.match(r"(licen[sc]e|copying)(\.|$)", f.lower()) for f in files):
        badges.append(f"![License](https://img.shields.io/github/license/{base})")
    if repo_data.get("language"):
        badges.append(f"![Top language](https://img.shields.io/github/languages/top/{base})")
    badges.append(f"![Stars](https://img.shields.io/github/stars/{base}?style=flat)")
    return badges


def build_tree(files, name="repo", max_lines=30):
    """A folder tree (two levels deep) made from the real file list. Folders first, then files, A to Z."""
    root = {}
    for path in files:
        parts = path.split("/")
        if any(p in SKIP or p.endswith(".pyc") for p in parts):
            continue
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        node.setdefault(parts[-1], None)
    lines = [f"{name}/"]

    def walk(node, prefix, depth):
        entries = sorted(node.items(), key=lambda kv: (kv[1] is None, kv[0].lower()))
        for i, (label, child) in enumerate(entries):
            last = i == len(entries) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{label}")
            if child is not None and depth < 2:
                walk(child, prefix + ("    " if last else "│   "), depth + 1)

    walk(root, "", 1)
    if len(lines) > max_lines:
        extra = len(lines) - max_lines + 1
        lines = lines[:max_lines - 1] + [f"… ({extra} more entries)"]
    return "\n".join(lines)