# US_FORMAT.md — User Story Format

## Purpose
This file defines how GitHubAssistant should generate user stories from a spec, and how Claude Code should interpret and implement them. Every user story must be detailed enough for Claude Code to work autonomously without asking clarifying questions.

---

## User Story Structure

Every GitHub issue must contain:

```
Title: [epic] short descriptive action-oriented title

Description:
What needs to be built, in plain language.
Why it exists and how it fits into the overall project.
Any constraints or requirements specific to this story.

Steps to cover:
1. Specific implementation step
2. Specific implementation step
3. Specific implementation step
...

Dependencies:
- List issue titles or numbers this story depends on
- Write "None" if no dependencies

Definition of Done:
- Specific, testable condition
- Specific, testable condition
- Specific, testable condition

Epic: epic-name
Label: epic-name
```

---

## Title Rules
- Always prefixed with epic in brackets: `[setup]`, `[search]`, `[output]`
- Action-oriented: starts with a verb — "implement", "create", "build", "add", "integrate"
- Specific: describes exactly what is being built
- Under 70 characters

Good titles:
- `[setup] initialise Python project structure and virtual environment`
- `[search] integrate Brave Search API with parallel execution`
- `[output] build Rich terminal verdict display panel`

Bad titles:
- `[setup] project setup`
- `search integration`
- `fix the output`

---

## Description Rules
- 3-5 sentences minimum
- Explains what, why, and how it fits
- References specific files, functions, or modules where known
- Mentions the spec section it comes from
- No vague language — every sentence adds information

Good description:
"Implement Brave Search API integration that accepts a search query string and returns a list of results with title, URL, snippet, and source tag `[brave]`. This is one of two search integrations (alongside Google Custom Search) that together provide independent index coverage for claim verification. Results feed into the deduplication and merging step before Claude analysis. Uses `BRAVE_API_KEY` from `.env`."

Bad description:
"Add Brave search so the app can search the web."

---

## Steps to Cover Rules
- Each step is one specific, implementable action
- Steps are ordered — dependencies respected within the story
- Include: implementation, error handling, logging, testing
- Reference specific libraries, functions, env vars where relevant
- Minimum 4 steps, no artificial maximum — as many as needed

Good steps:
```
1. Add `BRAVE_API_KEY` to `.env` and load via `python-dotenv`
2. Create `search/brave.py` module with `brave_search(query: str) -> list[dict]` function
3. Implement HTTP request to Brave Search API endpoint with query parameter
4. Parse response JSON — extract title, URL, snippet per result
5. Tag each result with `source: "brave"`
6. Add error handling — catch HTTP errors, API key missing, rate limit exceeded
7. Add Rich console logging for search progress
8. Test with sample query, verify result structure matches expected format
```

Bad steps:
```
1. Set up Brave API
2. Make it search
3. Return results
```

---

## Dependencies Rules
- List by issue title, not number (numbers change)
- Only hard dependencies — stories that must be done first
- If a story can be started in parallel, do not list it as a dependency

---

## Definition of Done Rules
- Each condition is testable — yes or no, not subjective
- Covers: functionality, error handling, integration with other components
- Minimum 3 conditions

Good definition of done:
```
- `brave_search("test query")` returns list of dicts with title, URL, snippet, source fields
- Missing or invalid API key raises clear error message and exits with code 1
- Rate limit exceeded returns empty list with warning, does not crash
- Results correctly tagged with `source: "brave"`
```

Bad definition of done:
```
- Works correctly
- No errors
- Tested
```

---

## Epic Guidelines

### `setup`
Covers: project structure, virtual environment, requirements.txt, .env template, .gitignore, README, logging configuration, base error handling

### `cli`
Covers: argument parsing with argparse, flag handling, input validation, help text, entry point

### `database` (if applicable)
Covers: SQLite schema, connection handling, CRUD operations, migration handling

### `[component-name]` (one per major stack component)
Covers: integration, API calls, data parsing, error handling, rate limiting

### `analysis`
Covers: Claude API prompts, response parsing, business logic (scoring, verdict, classification)

### `output`
Covers: Rich terminal formatting, interactive prompts, file export (PDF, txt, md)

### `testing`
Covers: unit tests, integration tests, edge case handling

---

## Issue Ordering on Board
Issues should be created in dependency order — foundational stories first:

1. `setup` epics always first
2. `cli` and `database` epics second
3. Component integration epics third
4. `analysis` epics fourth (depends on integrations)
5. `output` epics fifth (depends on analysis)
6. `testing` epics last

All issues assigned to **To Do** column on creation.

---

## Example User Story

```
Title: [search] integrate Brave Search API with parallel execution

Description:
Implement Brave Search API integration that accepts a search query string
and returns structured results tagged with their source index. Brave provides
independent search coverage focused on breadth and fringe sources, complementing
Google Custom Search which covers authoritative sources. Results from this
function feed into the deduplication step before Claude analysis. Requires
`BRAVE_API_KEY` in `.env`.

Steps to cover:
1. Add `BRAVE_API_KEY` to `.env` template and load via `python-dotenv`
2. Create `search/brave.py` module
3. Implement `brave_search(query: str) -> list[dict]` function
4. Make HTTP GET request to Brave Search API with query parameter
5. Parse JSON response — extract title, URL, snippet per result
6. Tag each result dict with `source: "brave"`
7. Implement error handling — missing API key, HTTP errors, rate limit, empty results
8. Add Rich console log: "Searching Brave... X results returned"
9. Test with sample query and verify result structure

Dependencies:
- [setup] initialise Python project structure and virtual environment
- [setup] configure .env and environment variable loading

Definition of Done:
- `brave_search("test query")` returns non-empty list of dicts with title, URL, snippet, source fields
- Missing API key raises descriptive error and exits with code 1
- HTTP error returns empty list with Rich warning, does not crash
- All results tagged with `source: "brave"`
- Rich progress log visible during execution

Epic: search
Label: search
```
