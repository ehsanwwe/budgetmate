\# AGENTS.md



\## Project handoff



This project was previously continued with Claude. Important historical context may exist in:

\- CLAUDE.md

\- PROGRESS.md



Before making changes, read these files first:

1\. CLAUDE.md

2\. PROGRESS.md

3\. README.md if present

4\. package.json / pyproject.toml / requirements.txt / docker-compose.yml / Dockerfile if present



\## Current priority



Use PROGRESS.md as the source of truth for what has already been done, what is pending, and what should not be repeated.



\## Working rules



\- Do not rewrite large parts of the project unless explicitly requested.

\- Do not audit the whole repository unless explicitly requested.

\- Before changing files, explain the intended change briefly.

\- Prefer minimal, targeted patches.

\- Preserve existing architecture and naming conventions.

\- Do not remove existing behavior unless the task explicitly asks for it.

\- After changes, run the smallest relevant test or build check.

\- If a command may be destructive, ask before running it.



\## Output expectations



When finishing a task, report:

\- Files changed

\- What changed

\- Commands/tests run

\- Any remaining risk or TODO

