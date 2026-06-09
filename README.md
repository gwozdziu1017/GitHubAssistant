# GitHubAssistant

A CLI tool that takes a `*_SPEC.md` project spec file, generates epics and detailed user stories using Claude Opus, then fully bootstraps a GitHub project — local repo, remote repo, project board, labels, and issues — ready for Claude Code to pick up and work on autonomously.

---

## What it does

1. Reads your `*_SPEC.md` spec file
2. Sends it to **Claude Opus** to auto-generate epics and detailed user stories
3. Displays a full execution plan and asks for confirmation
4. Creates a **local git repository** (`master` + `dev` branches)
5. Creates a **private/public GitHub repository** and pushes both branches
6. Creates a **GitHub Projects v2 board** with columns: To Do / In Progress / Blocked / Done
7. Creates **colour-coded epic labels**
8. Creates **GitHub issues** with full Description / Steps / Dependencies / Definition of Done bodies, labelled and placed in the To Do column

Every step is described in the terminal before execution and requires your explicit confirmation. The script also scans the spec for accidentally included API keys before sending anything anywhere.

---

## Requirements

- Python 3.10+
- [`gh` CLI](https://cli.github.com) installed and authenticated (`gh auth login`)
- An [Anthropic API key](https://console.anthropic.com)

---

## Installation

```bash
# Clone the repo
git clone https://github.com/gwozdziu1017/GitHubAssistant.git
cd GitHubAssistant

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up configuration
cp .env.example .env
# Edit .env and fill in your keys
```

---

## Configuration

Edit `.env` (never commit this file):

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GITHUB_USERNAME=your_github_username_here
DEFAULT_VISIBILITY=private   # or public
```

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key — used to generate epics and user stories |
| `GITHUB_USERNAME` | Your GitHub username — used when creating the remote repo |
| `DEFAULT_VISIBILITY` | Repository visibility: `private` (default) or `public` |

---

## Usage

```bash
python githubassistant.py path/to/YOUR_PROJECT_SPEC.md
```

### Example

```bash
python githubassistant.py ~/projects/WISE-MAN_SPEC.md
```

The script will walk you through 8 confirmed steps:

```
──────────────────────────────────────────────
  GITHUB ASSISTANT — Project Setup
  Input: WISE-MAN_SPEC.md
──────────────────────────────────────────────

╭─ Next step: Check prerequisites ───────────╮
│   Verify ANTHROPIC_API_KEY and             │
│   GITHUB_USERNAME are set in .env          │
│   Verify gh CLI is authenticated           │
╰────────────────────────────────────────────╯
  Proceed with this step? [y/n]:
```

After confirming all steps you will see a summary:

```
──────────────────────────────────────────────
  All done. wise-man is ready.
  12 issues waiting on the board.
  Repo:  https://github.com/you/wise-man
  Board: https://github.com/users/you/projects
──────────────────────────────────────────────
  Start with: gh issue list --repo you/wise-man --label setup
```

---

## Spec file format

Input files must follow the `*_SPEC.md` naming convention (e.g. `WISE-MAN_SPEC.md`).

See [`GithubAssistant/SPEC_FORMAT.md`](GithubAssistant/SPEC_FORMAT.md) for the full spec writing guide, and [`GithubAssistant/US_FORMAT.md`](GithubAssistant/US_FORMAT.md) for the user story format that Claude will follow when generating issues.

---

## Security

- `.env` is listed in `.gitignore` and will never be committed
- The script scans the spec file for API key patterns before sending it to Claude — it will abort with a clear error if a potential secret is detected
- Before every `git push`, the script verifies that `.gitignore` covers `.env`

---

## Project board columns

| Column | Purpose |
|---|---|
| To Do | All new issues land here |
| In Progress | Actively being worked on |
| Blocked | Waiting on a dependency or decision |
| Done | Completed and tested |

---

## Stack

| Component | Purpose |
|---|---|
| Python | Core language |
| `anthropic` | Claude Opus API — epic and user story generation |
| `gitpython` | Local repository initialisation |
| `gh` CLI | Remote repo, project board, labels, issues |
| `python-dotenv` | Load configuration from `.env` |
| `rich` | Terminal output, panels, confirmation prompts |
