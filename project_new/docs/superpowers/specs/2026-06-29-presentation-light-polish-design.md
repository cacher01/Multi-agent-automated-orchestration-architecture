# Presentation Light Polish Design

## Goal

Make the project easier to demonstrate and easier to understand without changing the core orchestration behavior.

This pass is intentionally lightweight. It should improve first impression, documentation clarity, and basic repository hygiene while avoiding large structural refactors.

## Scope

In scope:

- Improve the existing static UI under `app/static/`.
- Rewrite the root `README.md` as a clear project entry point.
- Adjust `.gitignore` so project documentation can be versioned.
- Fix current low-risk lint issues reported by `ruff`.
- Keep all current APIs and backend behavior compatible.

Out of scope:

- Splitting `Orchestrator` into workflow strategy modules.
- Introducing React, Vite, or another frontend build system.
- Adding authentication or multi-user ownership.
- Changing database technology.
- Redesigning the task/event schema.

## Frontend Design

Keep the current no-build static frontend. The UI should look less like a raw debug console and more like a focused orchestration workspace.

The page should make these areas clear:

- Task submission and example prompts.
- Current task status, workflow, and task id.
- Final answer, citations, and generated artifacts.
- Execution graph and node inspector.
- Task history and session task list.

The visual update should stay conservative:

- Use clearer section titles and empty states.
- Improve spacing, badges, and status colors.
- Keep the two-column layout on desktop and responsive single-column layout on small screens.
- Preserve the existing event stream and replay behavior.

## README Design

The README should be rewritten for a new reader. It should answer, in order:

1. What the project is.
2. What it can do.
3. How to run it.
4. How to try a useful demo task.
5. How the architecture is organized.
6. What workflows and tools exist.
7. What tests verify.
8. What safety boundaries and current limits exist.
9. What should be improved next.

The README should avoid long undifferentiated feature lists. It should use short sections, tables where useful, and explicit commands.

## Engineering Cleanup

This pass should fix only low-risk hygiene issues:

- Remove unused imports.
- Remove unused local variables that `ruff` reports.
- Keep public behavior unchanged.
- Keep tests passing.

No code movement is planned in this pass. The large `Orchestrator` file should be documented as a known next refactor, not fixed here.

## Verification

Run:

```powershell
conda run -n pytorch python -m pytest
conda run -n pytorch ruff check app tests
```

Success criteria:

- Existing tests pass.
- Ruff reports no issues for `app` and `tests`.
- README is readable as a standalone project overview.
- UI still works through `/ui` without new dependencies.

## Risks

- UI changes can accidentally break selectors used by `app.js`; keep element ids stable.
- README can overclaim production readiness; explicitly describe current limits.
- `.gitignore` changes may expose documentation that was previously ignored; keep secrets and runtime data ignored.
