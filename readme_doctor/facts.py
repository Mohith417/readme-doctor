"""Extract exact facts from ALL source files with plain code (no AI, no tokens, instant).

Tests, scripts, examples and docs are skipped for flags/variables/routes: they contain sample
values that are not part of the product. The README writer is given these facts so it does
not have to guess flags, env vars, routes, request fields or commands.
"""
import re

_CLI_LIBS = re.compile(r"\b(import click|from click|import argparse|from argparse|import typer|from typer)\b")
_FLAG = re.compile(r"""["'](-{1,2}[A-Za-z][\w-]*)["']""")
_ENV = re.compile(
    r"""(?:os\.getenv|os\.environ\.get|os\.environ\[|environ\.get|getenv)\(?\s*["']([A-Z][A-Z0-9_]+)["']"""
    r"""|process\.env\.([A-Z][A-Z0-9_]+)"""
)
_ROUTE = re.compile(r"""@\w+\.(route|get|post|put|delete|patch)\(\s*["']([^"']+)["']""")
_SCRIPT = re.compile(r"""["']([\w.-]+)\s*=\s*([\w.]+:[\w]+)["']""")
_RUN = re.compile(r"\b\w+\.run\(")
_SUBCOMMANDS = re.compile(r"@click\.group|\.add_command\(|@(?!click\b)\w+\.command\(")
_MARKER = re.compile(r"pytest\.mark\.(\w+)")

_SKIP_FOLDERS = {"tests", "test", "scripts", "examples", "example", "docs", "doc", "samples", "demo", "demos"}


def _is_product_file(path):
    """False for test, script, example and documentation files."""
    parts = path.replace("\\", "/").lower().split("/")
    name = parts[-1]
    if any(folder in _SKIP_FOLDERS for folder in parts[:-1]):
        return False
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return False
    if name.endswith(".md"):
        return False
    return True


def product_files(code_samples):
    """Only the product source files (tests, scripts, examples and docs removed)."""
    return {path: text for path, text in (code_samples or {}).items() if _is_product_file(path)}


def _cli_flags(code_samples):
    flags = set()
    for text in code_samples.values():
        if _CLI_LIBS.search(text):
            flags.update(_FLAG.findall(text))
    return sorted(f for f in flags if f not in ("-h", "--help"))


def _env_vars(code_samples):
    found = set()
    for text in code_samples.values():
        for match in _ENV.finditer(text):
            found.add(match.group(1) or match.group(2))
    return sorted(found)


def _routes(code_samples):
    found = set()
    for path, text in code_samples.items():
        if not path.endswith(".py"):
            continue
        for method, route in _ROUTE.findall(text):
            verb = "GET" if method in ("route", "get") else method.upper()
            found.add(f"{verb} {route}")
    return sorted(found)


def _body_fields(code_samples):
    """JSON/form fields the web API reads from the request body."""
    found = set()
    for path, text in code_samples.items():
        if not path.endswith(".py") or "request" not in text:
            continue
        for name in set(re.findall(r"(\w+)\s*=\s*request\.(?:get_json|json)", text)):
            found.update(re.findall(rf"\b{name}\.get\(\s*[\"'](\w+)[\"']", text))
        found.update(re.findall(r"request\.(?:json|form)\.get\(\s*[\"'](\w+)[\"']", text))
    return sorted(found)


def _run_commands(code_samples):
    """Files that start a server when run directly, e.g. python app.py."""
    return sorted(f"python {path}" for path, text in code_samples.items()
                  if path.endswith(".py") and _RUN.search(text) and "__main__" in text)


def _cli_shape(code_samples):
    texts = [t for t in code_samples.values() if _CLI_LIBS.search(t)]
    if not texts:
        return ""
    if any(_SUBCOMMANDS.search(t) for t in texts):
        return "the command line tool has subcommands"
    return "ONE command that takes repository URL(s) and flags; there are NO subcommands (do not invent 'analyze' or 'generate' commands)"


def _tests(code_samples):
    files = [p for p in code_samples
             if p.replace("\\", "/").split("/")[-1].startswith("test_") or p.endswith("_test.py")]
    if not files:
        return ""
    joined = "\n".join(code_samples[p] for p in files)
    runner = "pytest" if "pytest" in joined else ("python -m unittest" if "unittest" in joined else "plain Python scripts")
    markers = sorted(set(_MARKER.findall(joined)))
    return (f"{len(files)} test files; runner: {runner}; "
            f"custom pytest markers: {', '.join(markers) if markers else 'none (do not use -m)'}")


def _console_scripts(code_samples):
    found = []
    for path, text in code_samples.items():
        if path.endswith("setup.py") or path.endswith("pyproject.toml"):
            found += [f"{name} -> {target}" for name, target in _SCRIPT.findall(text)]
    return found


def _dependencies(code_samples):
    deps = []
    for path, text in code_samples.items():
        if path.endswith("requirements.txt"):
            deps += [line.strip() for line in text.splitlines()
                     if line.strip() and not line.startswith("#")]
    return deps


def extract_facts(code_samples):
    """Return a dict of facts found by reading every file completely."""
    code_samples = code_samples or {}
    product = product_files(code_samples)
    return {
        "files_total": len(code_samples),
        "files_read": len(product),
        "cli_flags": _cli_flags(product),
        "cli_shape": _cli_shape(product),
        "env_vars": _env_vars(product),
        "routes": _routes(product),
        "body_fields": _body_fields(product),
        "run_commands": _run_commands(product),
        "console_scripts": _console_scripts(product),
        "dependencies": _dependencies(product),
        "tests": _tests(code_samples),
    }


def format_facts(facts):
    """Turn the facts into a block of text for the AI prompt."""
    def line(label, items):
        return f"- {label}: {', '.join(items) if items else 'none found'}"

    skipped = facts["files_total"] - facts["files_read"]
    return "\n".join([
        f"FACTS FOUND BY CODE IN ALL {facts['files_read']} PRODUCT SOURCE FILES "
        f"({skipped} test/script/example files left out; complete and exact; "
        "mention ONLY flags, variables, routes, request fields and commands from this list):",
        line("Command-line flags", facts["cli_flags"]),
        f"- Command-line structure: {facts['cli_shape'] or 'not found'}",
        line("Environment variables", facts["env_vars"]),
        line("Web routes", facts["routes"]),
        line("JSON fields the API reads from the request body (use these exact names in curl examples)", facts["body_fields"]),
        line("Ways to start the web server directly", facts["run_commands"]),
        line("Console commands", facts["console_scripts"]),
        line("Dependencies (requirements.txt)", facts["dependencies"]),
        f"- Tests: {facts['tests'] or 'none found'}",
    ])
