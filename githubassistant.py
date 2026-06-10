#!/usr/bin/env python3
"""GitHubAssistant — Bootstrap a GitHub project from a *_SPEC.md file."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

import anthropic
from dotenv import load_dotenv
from git import Repo
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule

# Load .env from the directory where this script lives
load_dotenv(Path(__file__).parent / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")
DEFAULT_VISIBILITY = os.getenv("DEFAULT_VISIBILITY", "public")

console = Console()

# ---------------------------------------------------------------------------
# System prompt — bakes in user story format so the user only passes the spec
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a senior software architect generating GitHub issues from a project spec.

Analyse the spec and produce epics and detailed user stories.

EPIC RULES:
- Always include `setup` (project structure, venv, .env, .gitignore, README)
- One epic per major stack component (e.g. search, database, analysis)
- Include `cli` for argument handling and user interaction
- Include `output` for terminal/display formatting if applicable

USER STORY STRUCTURE (each story must include all fields):
- title: [epic] verb-led action under 70 chars
- description: 3-5 sentences — what, why, how it fits, constraints
- steps: minimum 4 specific implementable steps referencing real filenames, functions, env vars
- dependencies: list of story titles this depends on (empty list if none)
- definition_of_done: minimum 3 specific testable conditions

STORY ORDERING (by dependency):
1. setup stories first
2. cli and database stories second
3. Component integration stories third
4. analysis stories fourth
5. output stories fifth
6. testing stories last

OUTPUT: Return ONLY a JSON object — no prose, no markdown fences — with this exact schema:
{
  "epics": ["epic1", "epic2"],
  "stories": [
    {
      "title": "[epic] action-oriented title",
      "epic": "epic-name",
      "description": "3-5 sentence description",
      "steps": ["step 1", "step 2"],
      "dependencies": ["[epic] other story title"],
      "definition_of_done": ["condition 1", "condition 2"]
    }
  ]
}

Be specific. Use real file names, function signatures, and library names from the spec.
No vague language. Every step must be implementable without further clarification."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Patterns that suggest an API key or secret was left in the spec file.
# Each tuple is (label, regex).
_SECRET_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("Anthropic API key",       re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}")),
    ("OpenAI API key",          re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("GitHub token",            re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("Google API key",          re.compile(r"\bAIza[A-Za-z0-9\-_]{35}")),
    ("AWS access key",          re.compile(r"\bAKIA[A-Z0-9]{16}")),
    ("Generic high-entropy key",re.compile(r"(?<![a-zA-Z0-9])[A-Za-z0-9+/]{40,}(?![a-zA-Z0-9])")),
]


# ---------------------------------------------------------------------------
# Cache — stores Claude API responses keyed by spec content hash
# ---------------------------------------------------------------------------

CACHE_PATH = Path.home() / ".githubassistant_cache.json"


def _spec_hash(spec_content: str) -> str:
    """Return a SHA-256 hash of the spec content used as cache key."""
    return hashlib.sha256(spec_content.encode("utf-8")).hexdigest()


def load_cache() -> dict:
    """Load the cache file, returning an empty dict if it doesn't exist."""
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cache(cache: dict) -> None:
    """Persist the cache dict to disk."""
    try:
        CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except OSError as e:
        console.print(f"[yellow]⚠  Could not save cache: {e}[/yellow]")


def get_cached_stories(spec_content: str) -> Optional[dict]:
    """Return cached Claude response for this spec, or None if not cached."""
    cache = load_cache()
    return cache.get(_spec_hash(spec_content))


def set_cached_stories(spec_content: str, data: dict) -> None:
    """Store Claude response in cache keyed by spec hash."""
    cache = load_cache()
    cache[_spec_hash(spec_content)] = data
    save_cache(cache)


def scan_for_secrets(content: str, source_label: str) -> None:
    """Warn and abort if content appears to contain API keys or secrets."""
    hits: List[str] = []
    for label, pattern in _SECRET_PATTERNS:
        if pattern.search(content):
            hits.append(label)

    if not hits:
        return

    console.print()
    console.print(
        Panel(
            "\n".join(
                [f"[red]Possible secret detected in {source_label}:[/red]"]
                + [f"  • {h}" for h in hits]
                + [
                    "",
                    "Remove all secrets before proceeding.",
                    "Store keys in [bold].env[/bold] and reference them as environment variables.",
                ]
            ),
            title="[bold red]⚠  SECRET DETECTED[/bold red]",
            border_style="red",
        )
    )
    sys.exit(1)


def confirm_step(
    title: str,
    details: Union[List[str], Callable[[], List[str]]],
    on_decline: Optional[Callable] = None,
) -> None:
    """
    Show a step panel and ask the user to confirm before proceeding.

    details     — static list of strings, or a callable that returns one so the
                  panel refreshes after reconfiguration.
    on_decline  — optional callable invoked when the user presses n and chooses
                  to reconfigure. It should re-prompt whatever inputs are relevant
                  to this step and update state via nonlocal/closure. After it
                  returns, the panel is re-shown with fresh details.
                  If None, pressing n only offers Abort (nothing to reconfigure).
    """
    while True:
        console.print()
        current_details = details() if callable(details) else details
        body = "\n".join(f"  {d}" for d in current_details)
        console.print(
            Panel(body, title=f"[bold cyan]Next step: {title}[/bold cyan]", border_style="cyan")
        )

        if Confirm.ask("  Proceed with this step?"):
            return

        # User pressed n
        console.print()
        if on_decline:
            console.print("  [yellow]What would you like to do?[/yellow]")
            console.print("    [bold]r[/bold] — Reconfigure and review again")
            console.print("    [bold]a[/bold] — Abort the entire script")
            console.print()
            choice = Prompt.ask("  Your choice", choices=["r", "a"], default="r")
            if choice == "a":
                console.print("[yellow]Aborted by user.[/yellow]")
                sys.exit(0)
            on_decline()   # re-prompt inputs, update state; then loop to re-show panel
        else:
            # Nothing to reconfigure — confirm abort or loop back
            console.print("  [yellow]Nothing to reconfigure for this step.[/yellow]")
            console.print("    [bold]y[/bold] — Abort the entire script")
            console.print("    [bold]n[/bold] — Go back and review again")
            console.print()
            if Confirm.ask("  Abort the script?", default=False):
                console.print("[yellow]Aborted by user.[/yellow]")
                sys.exit(0)
            # n → loop back and re-show the panel


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a gh CLI command and return the result."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "No error details available."
        console.print(
            Panel(
                f"[red]Command:[/red] gh {' '.join(args)}\n\n"
                f"[red]Error:[/red] {stderr}",
                title="[bold red]✗ GitHub CLI error[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)
    return result


def gh_graphql(query: str) -> dict:
    """Execute a GitHub GraphQL query via gh api."""
    result = gh("api", "graphql", "-f", f"query={query}")
    data = json.loads(result.stdout)
    if "errors" in data:
        console.print(f"[red]✗ GraphQL error: {data['errors']}[/red]")
        sys.exit(1)
    return data


# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

def check_prerequisites() -> None:
    if not ANTHROPIC_API_KEY:
        console.print(
            Panel(
                "ANTHROPIC_API_KEY is not set.\n\n"
                "Add it to your shell profile (~/.zshrc or ~/.bashrc):\n"
                "  export ANTHROPIC_API_KEY=sk-ant-...\n\n"
                "Then reload your shell:  source ~/.zshrc",
                title="[bold red]✗ Missing ANTHROPIC_API_KEY[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)

    if not GITHUB_USERNAME:
        console.print(
            Panel(
                "GITHUB_USERNAME is not set.\n\n"
                "Add it to your shell profile (~/.zshrc or ~/.bashrc):\n"
                "  export GITHUB_USERNAME=your-username\n\n"
                "Then reload your shell:  source ~/.zshrc",
                title="[bold red]✗ Missing GITHUB_USERNAME[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)

    result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if result.returncode != 0:
        console.print(
            Panel(
                "gh CLI is not authenticated.\n\n"
                "Run:  gh auth login\n\n"
                f"Details: {result.stderr.strip()}",
                title="[bold red]✗ GitHub CLI not authenticated[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)

    console.print("[green]✓ Prerequisites OK[/green]")


# ---------------------------------------------------------------------------
# Spec reading
# ---------------------------------------------------------------------------

def read_spec(spec_path: Path) -> str:
    if not spec_path.exists():
        console.print(f"[red]✗ File not found: {spec_path}[/red]")
        sys.exit(1)

    if not spec_path.name.endswith("_SPEC.md"):
        console.print("[red]✗ File must follow *_SPEC.md naming convention[/red]")
        sys.exit(1)

    content = spec_path.read_text(encoding="utf-8").strip()
    if not content:
        console.print("[red]✗ Spec file is empty[/red]")
        sys.exit(1)

    console.print(f"[green]✓ Spec file read: {spec_path.name}[/green]")
    return content


# ---------------------------------------------------------------------------
# Epic and user story generation
# ---------------------------------------------------------------------------

def generate_stories(spec_content: str) -> dict:
    # Check cache before making an API call
    cached = get_cached_stories(spec_content)
    if cached:
        console.print("[green]✓ Using cached epics and stories (spec unchanged)[/green]")
        console.print(f"  Epics: {', '.join(cached.get('epics', []))}")
        console.print(f"  Stories: {len(cached.get('stories', []))} total")
        if Confirm.ask("  Use cached result? (n = regenerate via API)"):
            return cached
        console.print("[yellow]⠸ Regenerating via API...[/yellow]")

    console.print("[yellow]⠸ Analysing spec with Claude Opus...[/yellow]")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Generate epics and user stories for this project spec:\n\n"
                    + spec_content
                ),
            }
        ],
    )

    response_text = message.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped the JSON
    response_text = re.sub(r"^```[a-z]*\n?", "", response_text)
    response_text = re.sub(r"\n?```$", "", response_text)

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        # Fallback: extract the first {...} block
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not match:
            console.print(
                Panel(
                    "Claude did not return valid JSON.\n\n"
                    "This is unexpected — please try running the script again.",
                    title="[bold red]✗ Failed to parse Claude response[/bold red]",
                    border_style="red",
                )
            )
            sys.exit(1)
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            console.print(
                Panel(
                    "Claude's response was cut off before it could finish.\n\n"
                    "The spec may be too large for a single API call.\n"
                    "Try splitting the spec into smaller sections and running separately.",
                    title="[bold red]✗ Claude response truncated[/bold red]",
                    border_style="red",
                )
            )
            sys.exit(1)

    epics = data.get("epics", [])
    stories = data.get("stories", [])

    console.print(f"[green]✓ Epics generated: {', '.join(epics)}[/green]")
    console.print(f"[green]✓ User stories generated: {len(stories)} total[/green]")

    set_cached_stories(spec_content, data)
    console.print(f"[green]✓ Response cached to {CACHE_PATH}[/green]")

    return data


# ---------------------------------------------------------------------------
# Execution plan display
# ---------------------------------------------------------------------------

def display_plan(spec_path: Path, repo_name: str, data: dict) -> None:
    epics = data["epics"]
    stories = data["stories"]

    console.print()
    console.rule("[bold blue]GITHUB ASSISTANT — Execution Plan[/bold blue]")
    console.print()
    console.print(f"[bold]Input:[/bold]      {spec_path.name}")
    console.print(f"[bold]Repository:[/bold] {GITHUB_USERNAME}/{repo_name} ({DEFAULT_VISIBILITY})")
    console.print(f"[bold]Branches:[/bold]   master, dev")
    console.print()

    console.print("[bold]EPICS IDENTIFIED:[/bold]")
    for epic in epics:
        console.print(f"  • {epic}")
    console.print()

    console.print(f"[bold]USER STORIES ({len(stories)} total):[/bold]")
    for story in stories:
        console.print(f"  {story['title']}")
    console.print()

    console.print("[bold]PROJECT BOARD:[/bold]")
    console.print("  Columns: To Do, In Progress, Blocked, Done")
    console.print("  Issues assigned to: To Do")
    console.print()


# ---------------------------------------------------------------------------
# Local repository
# ---------------------------------------------------------------------------

def create_local_repo(repo_name: str, target_dir: Path) -> Path:
    repo_path = target_dir / repo_name

    if repo_path.exists():
        console.print(f"[yellow]⚠  Directory {repo_path} already exists[/yellow]")
        if not Confirm.ask("Continue anyway?"):
            sys.exit(0)
    else:
        repo_path.mkdir(parents=True)

    console.print("[yellow]⠸ Initialising local repository...[/yellow]")

    repo = Repo.init(repo_path)
    # Set default branch to master
    repo.git.symbolic_ref("HEAD", "refs/heads/master")

    # Seed with README and .gitignore so there is something to commit
    (repo_path / "README.md").write_text(
        f"# {repo_name}\n\nProject initialised by GitHubAssistant.\n"
    )
    (repo_path / ".gitignore").write_text(
        ".env\n__pycache__/\n*.pyc\n.venv/\nvenv/\n*.egg-info/\ndist/\nbuild/\n.DS_Store\n"
    )

    repo.index.add(["README.md", ".gitignore"])
    repo.index.commit("Initial commit")

    console.print(f"[green]✓ Local repository created: {repo_name}/[/green]")
    console.print("[green]✓ master branch set as default[/green]")

    repo.create_head("dev")
    console.print("[green]✓ dev branch created[/green]")

    return repo_path


# ---------------------------------------------------------------------------
# Remote repository
# ---------------------------------------------------------------------------

def create_remote_repo(repo_name: str) -> str:
    console.print("[yellow]⠸ Creating remote GitHub repository...[/yellow]")

    gh(
        "repo", "create",
        f"{GITHUB_USERNAME}/{repo_name}",
        f"--{DEFAULT_VISIBILITY}",
        "--description", f"{repo_name} — created by GitHubAssistant",
    )

    repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}"
    console.print(f"[green]✓ Remote repository created: {repo_url} ({DEFAULT_VISIBILITY})[/green]")
    return repo_url


def verify_gitignore_covers_env(repo_path: Path) -> None:
    """Abort if the repo's .gitignore does not cover .env — prevents accidental key publishing."""
    gitignore = repo_path / ".gitignore"
    if not gitignore.exists():
        console.print(
            Panel(
                "No .gitignore found in the repository.\n"
                "A .gitignore covering .env is required before pushing.",
                title="[bold red]⚠  MISSING .gitignore[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)

    lines = [l.strip() for l in gitignore.read_text().splitlines()]
    # Accept ".env", "*.env", ".env*"
    covered = any(re.fullmatch(r"\.env\*?|\*\.env", l) for l in lines if l and not l.startswith("#"))
    if not covered:
        console.print(
            Panel(
                ".gitignore does not include a rule for .env files.\n"
                "Add '.env' to .gitignore before pushing to prevent secrets leaking.",
                title="[bold red]⚠  .env NOT IGNORED[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)

    console.print("[green]✓ .gitignore covers .env — safe to push[/green]")


def push_branches(repo_path: Path, repo_name: str) -> None:
    verify_gitignore_covers_env(repo_path)

    repo = Repo(repo_path)
    remote_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}.git"
    repo.create_remote("origin", remote_url)
    console.print("[green]✓ Local connected to remote[/green]")

    console.print("[yellow]⠸ Pushing branches...[/yellow]")
    repo.git.push("origin", "master")
    console.print("[green]✓ master pushed[/green]")
    repo.git.push("origin", "dev")
    console.print("[green]✓ dev pushed[/green]")


# ---------------------------------------------------------------------------
# GitHub Project board (v2)
# ---------------------------------------------------------------------------

def create_project_board(repo_name: str) -> tuple[str, str, str, dict]:
    """
    Create a GitHub Projects v2 board.
    Returns (project_number, project_node_id, status_field_id, option_ids).
    option_ids maps column name -> option node ID.
    """
    console.print("[yellow]⠸ Creating GitHub Project board...[/yellow]")

    result = gh(
        "project", "create",
        "--owner", GITHUB_USERNAME,
        "--title", repo_name,
        "--format", "json",
    )
    project_data = json.loads(result.stdout)
    project_number = str(project_data["number"])
    project_id = project_data["id"]  # node ID

    console.print(f"[green]✓ Project board created: {repo_name}[/green]")

    # Fetch the Status field node ID
    fields_result = gh(
        "project", "field-list", project_number,
        "--owner", GITHUB_USERNAME,
        "--format", "json",
    )
    fields_data = json.loads(fields_result.stdout)

    status_field_id = None
    for field in fields_data.get("fields", []):
        if field.get("name") == "Status":
            status_field_id = field["id"]
            break

    if not status_field_id:
        console.print("[red]✗ Status field not found in project[/red]")
        sys.exit(1)

    # Replace default options with our four columns using GraphQL
    # updateProjectV2Field with singleSelectOptions replaces all options
    mutation = f"""
    mutation {{
      updateProjectV2Field(input: {{
        projectId: "{project_id}"
        fieldId: "{status_field_id}"
        singleSelectOptions: [
          {{name: "To Do",       color: GRAY,   description: ""}}
          {{name: "In Progress", color: YELLOW, description: ""}}
          {{name: "Blocked",     color: RED,    description: ""}}
          {{name: "Done",        color: GREEN,  description: ""}}
        ]
      }}) {{
        projectV2Field {{
          ... on ProjectV2SingleSelectField {{
            id
            options {{ id name }}
          }}
        }}
      }}
    }}
    """
    mutation_result = gh_graphql(mutation)

    updated_field = (
        mutation_result
        .get("data", {})
        .get("updateProjectV2Field", {})
        .get("projectV2Field", {})
    )
    option_ids: Dict[str, str] = {
        opt["name"]: opt["id"]
        for opt in updated_field.get("options", [])
    }

    console.print("[green]✓ Columns created: To Do, In Progress, Blocked, Done[/green]")
    return project_number, project_id, status_field_id, option_ids


# ---------------------------------------------------------------------------
# Epic labels
# ---------------------------------------------------------------------------

def create_labels(repo_name: str, epics: List[str]) -> None:
    console.print("[yellow]⠸ Creating epic labels...[/yellow]")
    colors = [
        "0075ca", "e4e669", "d73a4a", "0e8a16",
        "7057ff", "008672", "e99695", "f9d0c4",
    ]
    for i, epic in enumerate(epics):
        color = colors[i % len(colors)]
        gh(
            "label", "create", epic,
            "--repo", f"{GITHUB_USERNAME}/{repo_name}",
            "--color", color,
            "--description", f"Epic: {epic}",
            "--force",
        )
        console.print(f"[green]✓ Label created: {epic}[/green]")


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

def format_issue_body(story: dict) -> str:
    steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(story["steps"]))
    deps = (
        "\n".join(f"- {d}" for d in story["dependencies"])
        if story["dependencies"]
        else "None"
    )
    dod = "\n".join(f"- {c}" for c in story["definition_of_done"])

    return (
        f"## Description\n{story['description']}\n\n"
        f"## Steps to cover\n{steps}\n\n"
        f"## Dependencies\n{deps}\n\n"
        f"## Definition of Done\n{dod}\n\n"
        f"**Epic:** {story['epic']}"
    )


def create_issues(
    repo_name: str,
    stories: List[dict],
    project_number: str,
    project_id: str,
    status_field_id: str,
    option_ids: dict,
) -> None:
    console.print("[yellow]⠸ Creating issues...[/yellow]")

    todo_option_id = option_ids.get("To Do")
    if not todo_option_id:
        console.print("[red]✗ 'To Do' option ID not found[/red]")
        sys.exit(1)

    for i, story in enumerate(stories, start=1):
        # Create the issue
        result = gh(
            "issue", "create",
            "--repo", f"{GITHUB_USERNAME}/{repo_name}",
            "--title", story["title"],
            "--body", format_issue_body(story),
            "--label", story["epic"],
        )
        issue_url = result.stdout.strip()

        # Add issue to project board
        item_result = gh(
            "project", "item-add", project_number,
            "--owner", GITHUB_USERNAME,
            "--url", issue_url,
            "--format", "json",
        )
        item_data = json.loads(item_result.stdout)
        item_id = item_data["id"]

        # Set status to "To Do"
        gh(
            "project", "item-edit",
            "--id", item_id,
            "--field-id", status_field_id,
            "--project-id", project_id,
            "--single-select-option-id", todo_option_id,
        )

        console.print(f"[green]✓ Issue #{i} created: {story['title']}[/green]")

    console.print(f"[green]✓ All {len(stories)} issues assigned to To Do[/green]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap a GitHub project from a *_SPEC.md file"
    )
    parser.add_argument("spec", help="Path to the *_SPEC.md spec file")
    args = parser.parse_args()

    spec_path = Path(args.spec).resolve()

    console.rule("[bold blue]GITHUB ASSISTANT — Project Setup[/bold blue]")
    console.print(f"[bold]Input:[/bold] {spec_path.name}")
    console.print()

    # ── Step 0: prerequisites ────────────────────────────────────────────────
    confirm_step(
        "Check prerequisites",
        [
            "Verify ANTHROPIC_API_KEY and GITHUB_USERNAME are set in .env",
            "Verify gh CLI is authenticated",
        ],
    )
    check_prerequisites()

    # ── Step 1: read and scan spec ───────────────────────────────────────────
    confirm_step(
        "Read spec file",
        [
            f"Read: {spec_path}",
            "Scan spec content for accidentally included API keys or secrets",
        ],
    )
    spec_content = read_spec(spec_path)
    scan_for_secrets(spec_content, spec_path.name)
    console.print("[green]✓ No secrets detected in spec file[/green]")

    # ── Step 2: generate epics and stories ──────────────────────────────────
    confirm_step(
        "Generate epics and user stories (Claude Opus API call)",
        [
            "Send spec to claude-opus-4-8",
            "Receive epics and detailed user stories as JSON",
            "Note: this call uses your Anthropic API quota",
        ],
    )
    data = generate_stories(spec_content)

    # ── Collect repo name and target directory ───────────────────────────────
    # Stored as a mutable container so the nested on_decline closure can update them.
    state: Dict[str, object] = {
        "repo_name": "",
        "target_dir": Path.home() / "Coding",
    }

    def prompt_repo_details() -> None:
        """Re-prompt repo name and target directory, updating shared state."""
        default_dir = state["target_dir"]
        while True:
            console.print()
            name = Prompt.ask("[bold]Enter repository name[/bold]").strip()
            if not name:
                console.print("[red]✗ Repository name cannot be empty — try again[/red]")
                continue
            if not re.match(r"^[a-zA-Z0-9._-]+$", name):
                console.print(
                    "[red]✗ Invalid name — letters, numbers, hyphens, underscores, dots only[/red]"
                )
                continue

            raw_dir = Prompt.ask(
                "[bold]Where should the local repo be created?[/bold]",
                default=str(default_dir),
            ).strip()
            resolved = Path(raw_dir).expanduser().resolve()
            state["repo_name"] = name
            state["target_dir"] = resolved
            break

    # Run once immediately to populate state before the first confirm_step
    prompt_repo_details()

    def repo_step_details() -> List[str]:
        """Return current step-3 details — re-evaluated after every reconfigure."""
        tdir = state["target_dir"]
        rname = state["repo_name"]
        lines = [
            f"Create directory: {tdir / rname}",
            "Initialise git with master as default branch",
            "Create README.md and .gitignore (includes .env rule)",
            "Make initial commit on master",
            "Create dev branch",
        ]
        if not tdir.exists():
            lines.append(f"⚠  {tdir} does not exist — it will be created")
        return lines

    def remote_step_details() -> List[str]:
        return [
            f"Create: github.com/{GITHUB_USERNAME}/{state['repo_name']} ({DEFAULT_VISIBILITY})",
            "This action is visible on your GitHub account",
        ]

    display_plan(spec_path, str(state["repo_name"]) or "—", data)

    if not Confirm.ask("[bold]Proceed with full execution?[/bold]"):
        console.print("[yellow]Aborted.[/yellow]")
        sys.exit(0)

    console.print()
    console.rule("[bold blue]Executing[/bold blue]")
    console.print()

    # Convenience accessors — read from state after all confirmations are done
    def repo_name() -> str:
        return str(state["repo_name"])

    def target_dir() -> Path:
        return Path(str(state["target_dir"]))

    # ── Step 3: local repository ─────────────────────────────────────────────
    confirm_step(
        "Create local repository",
        details=repo_step_details,
        on_decline=prompt_repo_details,
    )
    repo_path = create_local_repo(repo_name(), target_dir())

    # ── Step 4: remote repository ────────────────────────────────────────────
    confirm_step(
        "Create remote GitHub repository",
        details=remote_step_details,
    )
    create_remote_repo(repo_name())

    # ── Step 5: push branches ────────────────────────────────────────────────
    confirm_step(
        "Push branches to remote",
        details=[
            "Verify .gitignore covers .env before pushing",
            "Connect local repo to origin",
            "Push master branch",
            "Push dev branch",
        ],
    )
    push_branches(repo_path, repo_name())

    # ── Step 6: project board ────────────────────────────────────────────────
    confirm_step(
        "Create GitHub Project board",
        details=lambda: [
            f"Create Projects v2 board titled: {repo_name()}",
            "Set Status columns: To Do, In Progress, Blocked, Done (via GraphQL)",
        ],
    )
    project_number, project_id, status_field_id, option_ids = create_project_board(repo_name())

    # ── Step 7: labels ───────────────────────────────────────────────────────
    confirm_step(
        "Create epic labels",
        details=[f"Create label: {epic}" for epic in data["epics"]],
    )
    create_labels(repo_name(), data["epics"])

    # ── Step 8: issues ───────────────────────────────────────────────────────
    confirm_step(
        f"Create {len(data['stories'])} GitHub issues",
        [
            f"Create {len(data['stories'])} issues with full Description / Steps / DoD bodies",
            "Apply epic labels to each issue",
            "Add each issue to the project board",
            "Set status to To Do for all issues",
        ],
    )
    create_issues(
        repo_name(),
        data["stories"],
        project_number,
        project_id,
        status_field_id,
        option_ids,
    )

    console.print()
    console.rule("[bold green]All done[/bold green]")
    console.print()
    console.print(f"  [bold]{repo_name()}[/bold] is ready.")
    console.print(f"  {len(data['stories'])} issues waiting on the board.")
    console.print(f"  Repo:  https://github.com/{GITHUB_USERNAME}/{repo_name()}")
    console.print(f"  Board: https://github.com/users/{GITHUB_USERNAME}/projects")
    console.print()
    console.print(f"  Start with:  gh issue list --repo {GITHUB_USERNAME}/{repo_name()} --label {data['epics'][0]}")
    console.print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user. Exiting.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(
            Panel(
                f"{type(e).__name__}: {e}\n\n"
                "If this keeps happening, check your .env / shell config and gh auth status.",
                title="[bold red]✗ Unexpected error[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)
