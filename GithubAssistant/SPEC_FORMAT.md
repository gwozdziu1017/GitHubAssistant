# SPEC_FORMAT.md — Claude Spec Writing Rules

## Purpose
This file defines how Claude should structure every project spec written in collaboration with the user. Following this format ensures every spec is immediately usable by GitHubAssistant for epic generation, user story creation, and GitHub bootstrapping.

---

## File Naming
- Always name spec files: `PROJECTNAME_SPEC.md`
- Use uppercase project name, underscore before SPEC
- Examples: `WISE-MAN_SPEC.md`, `CYBER-PARLA_SPEC.md`, `AUDIO-TRANSCRIBER_SPEC.md`

---

## Required Sections
Every spec must contain all of the following sections in this order:

### 1. Title & Overview
- H1 title: `# Project Name — Short Description`
- Overview paragraph: what the project does, why it exists, who uses it
- Must be specific enough for Claude to extract epics from

### 2. CLI Usage
- Exact commands with all flags documented
- One example per usage pattern
- Explain what each flag does

### 3. Input
- Format, naming convention, content structure
- Concrete examples
- Edge cases and constraints

### 4. Stack
- Always use a table: Component | Purpose
- Every component must have a clear stated purpose
- No orphaned entries — if it's in the stack, explain why

### 5. Flow
- Numbered steps, one action per step
- Specific enough that each step could become a user story
- Include error handling steps where relevant
- Include state management steps where relevant

### 6. Output
- Exact format with real example output in code blocks
- All output modes documented separately
- Interactive prompts shown in context

### 7. Key Design Decisions
- Bold the decision, explain the reasoning after the dash
- Every non-obvious architectural choice must be here
- This section is critical for epic and user story generation

### 8. Configuration — .env
- Full `.env` template with all keys
- Every key explained

### 9. API Keys Required
- Simple list of all required keys
- Include any third-party account requirements

### 10. Notes
- Pricing information where relevant
- Performance considerations
- Known limitations
- Dependencies between components

---

## Writing Rules

**Be specific, not general**
Bad: "script processes files"
Good: "script reads all `.pdf` files from `SOURCE_DIR`, parses dates from filenames in `parla-session-dd-mm-yyyy.pdf` format, skips files already in SQLite database"

**State the why behind every decision**
Bad: "use SQLite"
Good: "SQLite — stateful session storage, enables pattern recognition across sessions without re-processing files"

**Use concrete examples everywhere**
- File naming: show actual filename e.g. `parla-session-31-05-2026.pdf`
- CLI: show actual command e.g. `python wiseman.py -d "Elvis Presley is alive"`
- Output: show actual rendered output in code blocks

**Tables for structured data**
Use tables for: stack, configuration, file properties, output types, credibility tiers — anything with two or more attributes

**No ambiguous language**
Avoid: "handle errors appropriately", "process the data", "output results"
Use: "display Rich error panel with message and exit code 1", "extract text using trafilatura", "print verdict panel with confidence level"

---

## Epic-Friendly Writing
GitHubAssistant auto-generates epics from the spec. To ensure clean epic generation:

- Each major component in the Stack should map to at least one epic
- Flow steps should cluster naturally into logical groups
- Key Design Decisions should reference the same components as the Stack
- Avoid mixing concerns in single flow steps

Typical epic pattern:
- `setup` — always present, covers project structure, dependencies, .env, virtual environment
- One epic per major Stack component (e.g. `search`, `database`, `analysis`, `output`)
- `cli` — argument handling, flags, user interaction
- `testing` — if applicable

---

## Spec Quality Checklist
Before finalising any spec, verify:
- [ ] Every stack component has a stated purpose
- [ ] Flow is specific enough for user story generation
- [ ] All CLI flags documented with examples
- [ ] Real example output shown in code blocks
- [ ] All .env keys listed with full template
- [ ] Key design decisions explain the why, not just the what
- [ ] File naming conventions shown with real examples
- [ ] No ambiguous language — every action is specific
