"""Deterministic README scoring: the same README + repo files always give the same score."""
import re
from dataclasses import dataclass

NO_README = "No README found"
FENCE = re.compile(r"(```|~~~).*?(?:\1|\Z)", re.S)


@dataclass(frozen=True)
class Check:
    key: str
    points: int
    passed: bool
    issue: str
    fix: str


def _split(text):
    """Return (prose without code blocks, list of code blocks)."""
    return FENCE.sub("", text), [m.group(0) for m in FENCE.finditer(text)]


def _headings(prose):
    found = [m.group(1) for m in re.finditer(r"^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", prose, re.M)]
    found += [m.group(1) for m in re.finditer(r"^(.+)\n=+[ \t]*$", prose, re.M)]
    found += [re.sub(r"<[^>]+>", "", m.group(1))
              for m in re.finditer(r"<h[1-6][^>]*>(.*?)</h[1-6]>", prose, re.I | re.S)]
    return [h.strip().lower() for h in found if h.strip()]


def _plain_text(prose):
    t = re.sub(r"<[^>]+>", " ", prose)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^ {0,3}#{1,6}.*$", " ", t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()


INSTALL_COMMANDS = (r"pip3? install|npm (install|i )|yarn (add|install)|pnpm (add|install)|mvn |gradle|"
                    r"cargo (install|build|add)|go (install|get|build)|git clone|docker (run|pull|build)|"
                    r"brew install|apt(-get)? install|setup\.py|make install|dotnet |composer require|"
                    r"gem install|conda install")


def evaluate_readme(readme, file_structure=()):
    """Return {"score": 0-100, "has_readme": bool, "checks": [Check, ...]}."""
    text = (readme or "").strip()
    if not text or text == NO_README:
        return {"score": 0, "has_readme": False, "checks": []}

    prose, code = _split(text)
    heads = _headings(prose)
    lower = text.lower()
    code_text = "\n".join(code).lower()
    inline = " ".join(re.findall(r"`([^`\n]+)`", prose)).lower()
    names = [f.split("/")[-1].lower() for f in file_structure]

    def head(pattern):
        return any(re.search(pattern, h) for h in heads)

    has_title = bool(re.search(r"^ {0,3}#[ \t]+\S", prose, re.M)
                     or re.search(r"^.+\n=+[ \t]*$", prose, re.M)
                     or re.search(r"<h1", prose, re.I))
    has_license_file = any(re.match(r"(licen[sc]e|copying)(\.|$)", n) for n in names)
    has_contrib_file = any(n.startswith("contributing") for n in names)

    checks = [
        Check("title", 8, has_title,
              "There is no top-level title.",
              "Start the README with a clear project title (# Project Name)."),
        Check("description", 7, len(_plain_text(prose)) >= 200,
              "The README has very little descriptive text.",
              "Add a few sentences explaining what the project is and who it is for."),
        Check("problem", 10,
              head(r"about|overview|what is|what it does|why|introduction|intro|description|features|"
                   r"motivation|background|problem|purpose|highlights"),
              "It does not explain what the project does or why it exists.",
              "Add an 'About' or 'Why' section that states the problem the project solves."),
        Check("install_section", 10,
              head(r"install|setup|set up|getting started|quick ?start|build|download|deploy"),
              "There is no installation or setup section.",
              "Add an 'Installation' section with step-by-step setup instructions."),
        Check("install_commands", 5,
              bool(re.search(INSTALL_COMMANDS, code_text) or re.search(INSTALL_COMMANDS, inline)),
              "No installation commands are shown.",
              "Show the exact install commands in a code block (for example pip install, npm install or git clone)."),
        Check("usage_section", 10,
              head(r"usage|example|how to|quick ?start|getting started|demo|tutorial|commands|reference"),
              "There is no usage or examples section.",
              "Add a 'Usage' section showing how to run the project."),
        Check("code_examples", 10, len(code) >= 1 or "<pre" in lower,
              "There are no code or command examples.",
              "Add code blocks with real commands or snippets people can copy."),
        Check("prerequisites", 8,
              head(r"prerequisite|requirement|dependenc|before you begin|what you need|compatib|supported")
              or bool(re.search(r"requires? (python|node|java|go|rust)|python ?>?=? ?3|python ?3\.\d|"
                                r"node(\.js)? ?v?\d|jdk ?\d|java ?\d+", lower)),
              "Prerequisites or required versions are not mentioned.",
              "List what must be installed first, including minimum versions (for example Python 3.10+)."),
        Check("license", 8,
              head(r"licen[sc]e") or has_license_file
              or bool(re.search(r"mit license|apache license|bsd[- ]\d|gnu general public", lower)),
              "No license information was found.",
              "Add a License section and a LICENSE file."),
        Check("contributing", 7,
              head(r"contribut|development|developing|pull request|how to help") or has_contrib_file,
              "There are no contribution guidelines.",
              "Add a short Contributing section, or a CONTRIBUTING.md file."),
        Check("structure", 5, len(heads) >= 3,
              "The README has little structure (fewer than 3 headings).",
              "Organise the README into sections with headings."),
        Check("troubleshooting", 4,
              head(r"troubleshoot|faq|common (issues|problems|errors)|known issues|support|getting help|help"),
              "There is no troubleshooting or help section.",
              "Add common errors and fixes, or say where to get help."),
        Check("badges", 4,
              bool(re.search(r"shields\.io|badge|!\[[^\]]*\]\(|<img", lower)),
              "There are no badges or images.",
              "Add badges (build status, license, version) or a screenshot."),
        Check("length", 4, len(text) >= 800,
              "The README is very short.",
              "Expand the README so a newcomer can get started without reading the code."),
    ]
    return {"score": sum(c.points for c in checks if c.passed), "has_readme": True, "checks": checks}


def issues(result):
    """Plain-language problems, biggest gaps first. Always the same for the same input."""
    if not result["has_readme"]:
        return ["The repository has no README file."]
    failed = [c for c in result["checks"] if not c.passed]
    return [c.issue for c in sorted(failed, key=lambda c: -c.points)]


def suggestions(result):
    if not result["has_readme"]:
        return ["Create a README.md with a title, description, installation, usage, license and contributing sections."]
    failed = [c for c in result["checks"] if not c.passed]
    return [c.fix for c in sorted(failed, key=lambda c: -c.points)]