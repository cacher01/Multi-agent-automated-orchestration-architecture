# Presentation Light Polish Design

## Goal

Improve the project's presentation quality while keeping the application behavior stable.

This pass is not a refactor sprint. The goal is to make the current project easier to show, easier to start, and easier to understand from the repository entry point.

## Scope

In scope:

- Polish the existing `/ui` page so it is clearer during demos.
- Rewrite `README.md` in a standard GitHub project style.
- Fix only small repository hygiene issues that affect presentation or basic quality checks.
- Keep all current backend APIs and orchestration behavior unchanged.

Out of scope:

- Splitting or redesigning the orchestrator.
- Reorganizing backend packages.
- Introducing a frontend framework or build step.
- Adding authentication, deployment automation, or production multi-user features.
- Changing workflow semantics, database schema, or tool behavior.

## UI Presentation

The current UI should remain a static HTML/CSS/JS page. The update should focus on presentation and readability:

- Make the project identity clearer at the top of the page.
- Make task input, examples, status, result, sources, artifacts, execution graph, and history easier to scan.
- Improve labels and empty states so the page works well in a live demo before and after a task runs.
- Keep existing element ids and API calls stable.

No desktop-specific redesign is required. The page only needs to remain usable on common browser sizes.

## README Style

Rewrite the README to match common GitHub project conventions. It should be concise and practical, not a long design document.

Recommended structure:

1. Project name and one-sentence summary.
2. What the project does.
3. Key features.
4. Screens/UI entry point.
5. Quick start.
6. Environment variables.
7. Example tasks.
8. Project structure.
9. Tests.
10. Current limitations.

The README should primarily explain:

- The project content.
- Typical applications.
- How to start and verify it.
- What capabilities are currently implemented.

It should avoid overclaiming production readiness.

## Minimal Code Hygiene

Only make low-risk cleanup needed for a clean presentation:

- Fix current `ruff` unused import / unused variable issues.
- Keep `.env`, runtime data, caches, and artifacts ignored.
- Keep Markdown documentation trackable in Git.

Do not move core code in this pass. Larger structural work can be planned separately after the project presentation is improved.

## Verification

Run:

```powershell
conda run -n pytorch python -m pytest
conda run -n pytorch ruff check app tests
```

Success criteria:

- Tests pass.
- Ruff passes.
- `/ui` still works with the existing API.
- README is short, clear, and useful as the repository landing page.

## Notes

The orchestrator is intentionally left unchanged in this pass. Its structure can be addressed later as a separate engineering task.
