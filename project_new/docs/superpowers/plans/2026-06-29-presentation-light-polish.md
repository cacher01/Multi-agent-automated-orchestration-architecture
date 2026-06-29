# Presentation Light Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve demo readability and repository clarity without changing runtime behavior.

**Architecture:** Keep the current FastAPI backend and static `/ui` frontend. Update only presentation files, README content, and low-risk lint issues. Do not split the orchestrator or reorganize backend modules.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, SQLite, vanilla HTML/CSS/JavaScript, pytest, ruff.

---

## File Structure

- Modify `README.md`: replace the current long feature list with a concise GitHub-style project overview.
- Modify `app/static/index.html`: improve labels, headings, example prompt copy, and visible structure while keeping element ids stable.
- Modify `app/static/styles.css`: polish spacing, cards, status badges, empty states, and readability without adding dependencies.
- Modify `app/static/app.js`: adjust visible text and small UI metadata only if needed; do not change API calls or event handling semantics.
- Modify `app/main.py`: remove unused import reported by ruff.
- Modify `app/orchestration/json_repair.py`: remove unused import reported by ruff.
- Modify `app/orchestration/orchestrator.py`: remove unused local variables reported by ruff without changing control flow.
- Modify `tests/test_llm_tools.py`: remove unused import reported by ruff.

## Task 1: Rewrite README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace README with concise GitHub-style structure**

Use this structure and keep command examples PowerShell-friendly:

```markdown
# Multi-Agent Dynamic Orchestration Framework

Lightweight FastAPI-based runtime for experimenting with dynamic multi-agent task orchestration, tool use, event replay, and source-grounded research workflows.

## What It Does

This project accepts a natural-language task, routes it to an execution workflow, optionally calls safe tools, records events, and returns a structured result through an API and a minimal web UI.

Typical use cases:

- Run source-grounded research tasks with citations.
- Test workflow routing across direct, planning, research, ReAct, supervisor, DAG, and experimental swarm paths.
- Observe task execution through persisted events and a browser UI.
- Generate task-scoped Markdown, text, JSON, CSV, or ZIP artifacts.

## Key Features

| Area | Support |
| --- | --- |
| Backend | FastAPI service with SQLite persistence |
| LLM | OpenAI-compatible client, tested with DeepSeek-style configuration |
| Workflows | `direct`, `plan_execute`, `research`, `react`, `supervisor`, `dag`, `swarm` |
| Tools | Search, safe web fetch, weather, time, calculator, date, unit conversion |
| Artifacts | Task-scoped Markdown, text, JSON, CSV, and ZIP files |
| Observability | Event history, SSE stream, replay endpoint, execution graph events |
| Tests | Mock-driven pytest suite for workflows, tools, API, artifacts, and safety |

## UI

Start the server and open:

```text
http://127.0.0.1:8000/ui
```

The UI supports task submission, session selection, live task status, final answer rendering, citations, artifacts, execution graph events, and task replay.

## Quick Start

```powershell
conda run -n pytorch python -m pytest
conda run -n pytorch python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000/ui
```

## Environment

Required for real LLM calls:

```powershell
$env:LLM_BASE_URL='https://api.deepseek.com'
$env:LLM_API_KEY='your-api-key'
$env:LLM_MODEL='deepseek-chat'
```

Optional for research and tool-backed tasks:

```powershell
$env:TAVILY_API_KEY='your-tavily-key'
$env:WEATHER_API_KEY='your-weatherapi-key'
$env:ARTIFACT_ROOT='artifacts'
```

The project also supports a local `.env` file. Keep `.env` out of Git.

## Example Tasks

```text
查询北京天气和当地时间
```

```text
调研特斯拉公司，概括业务、财务、竞争格局和近期动态，并给出引用
```

```text
先调研特斯拉公司基本情况，再分析其竞争格局，最后生成风险报告
```

```text
生成一份多智能体框架调研报告并保存为 Markdown 文件
```

## Project Structure

```text
app/
  main.py                  FastAPI application and route wiring
  core/                    Settings, enums, shared errors
  db/                      SQLite setup and repository methods
  orchestration/           Router, prompts, JSON repair, orchestrator
  agents/                  Task-scoped sub-agent runtime helpers
  tools/                   Tool registry, policy, executor, built-in tools
  services/                Task, event, result, and artifact services
  static/                  Minimal browser UI
tests/                     Mock-driven automated tests
scripts/                   Optional real-provider verification scripts
docs/                      Design and implementation notes
```

## API Overview

Main endpoints:

- `POST /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/stream`
- `GET /tasks/{task_id}/result`
- `GET /tasks/{task_id}/replay`
- `GET /tasks/{task_id}/artifacts`
- `POST /tasks/{task_id}/cancel`
- `POST /sessions`
- `POST /sessions/{session_id}/tasks`

## Testing

```powershell
conda run -n pytorch python -m pytest
conda run -n pytorch ruff check app tests
```

Automated tests use mock LLM/search/weather responses and do not require external API keys.

## Current Limits

- The project is a local research/demo framework, not a production multi-tenant service.
- There is no authentication or user ownership model.
- SQLite and local files are used for persistence.
- The orchestrator is intentionally still centralized and can be split later.
- Real research quality depends on configured LLM and search providers.

## License

Add a license file before publishing the repository publicly.
```

- [ ] **Step 2: Check README for overclaims**

Run:

```powershell
Select-String -Path README.md -Pattern "production|enterprise|secure multi-tenant"
```

Expected: no claims that present the project as production-ready.

## Task 2: Polish Static UI

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/styles.css`
- Optional modify: `app/static/app.js`

- [ ] **Step 1: Update visible labels without changing ids**

In `app/static/index.html`, keep every existing `id` value. Update visible product copy to this style:

```html
<title>Orchestration Workspace</title>
...
<strong>Orchestration Workspace</strong><small>Dynamic multi-agent runtime</small>
...
<div><span>Task Input</span><h1>Describe a task and let the orchestrator route it</h1></div>
...
<article id="finalAnswer" class="answer empty">Run a task to see the final answer, citations, and generated artifacts.</article>
```

Update prompt button labels to be clearer:

```html
<button type="button" data-prompt="查询北京天气和当地时间">Weather + Time</button>
<button type="button" data-prompt="调研特斯拉公司，概括业务、财务、竞争格局和近期动态，并给出引用">Research Report</button>
<button type="button" data-prompt="分析多智能体框架的发展趋势、代表项目、风险和适用场景">Multi-angle Analysis</button>
<button type="button" data-prompt="先调研特斯拉公司基本情况，再分析其竞争格局，最后生成风险报告">DAG Workflow</button>
```

- [ ] **Step 2: Add compact capability hint**

Add a short static helper line below the prompt buttons:

```html
<p class="composer-hint">Routes tasks across direct answers, research, ReAct tools, supervisor analysis, DAG execution, and experimental swarm runs.</p>
```

- [ ] **Step 3: Improve CSS card hierarchy**

In `app/static/styles.css`, add or adjust these styles:

```css
.task-composer {
  border-top: 4px solid var(--blue);
}

.result-panel {
  border-top: 4px solid var(--green);
}

.composer-hint {
  width: 100%;
  margin-top: 8px;
  color: var(--muted);
  font-size: 12px;
}

.runtime-panel {
  box-shadow: 0 1px 2px rgba(16, 24, 40, .04);
}

.empty-state,
.answer.empty {
  color: #7a8699;
}
```

Keep existing responsive media queries. Do not add a frontend dependency or build step.

- [ ] **Step 4: Smoke-check UI selectors**

Run:

```powershell
conda run -n pytorch python -m pytest tests/test_markdown_ui.py tests/test_api.py tests/test_artifact_api.py
```

Expected: pass. These tests catch broken static page serving and basic UI/API assumptions.

## Task 3: Fix Low-Risk Ruff Issues

**Files:**
- Modify: `app/main.py`
- Modify: `app/orchestration/json_repair.py`
- Modify: `app/orchestration/orchestrator.py`
- Modify: `tests/test_llm_tools.py`

- [ ] **Step 1: Remove unused imports**

Apply these edits:

```python
# app/main.py
# Remove:
import asyncio

# app/orchestration/json_repair.py
# Change:
from typing import Any, TypeVar
# To:
from typing import TypeVar

# tests/test_llm_tools.py
# Remove:
import pytest
```

- [ ] **Step 2: Remove unused local variables in orchestrator**

In `app/orchestration/orchestrator.py`, remove assignments like:

```python
task = self.repository.get_task(task_id)
```

from workflow methods where `task` is never used. Keep surrounding checkpoint and context calls unchanged.

Known locations from current ruff output:

- `_run_direct`
- `_run_plan_execute`
- `_run_research`
- `_run_supervisor`
- `_run_dag`
- `_run_swarm`

- [ ] **Step 3: Run ruff**

Run:

```powershell
conda run -n pytorch ruff check app tests
```

Expected: no ruff errors.

## Task 4: Full Verification

**Files:**
- No code files unless verification reveals a regression.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
conda run -n pytorch python -m pytest
```

Expected: all tests pass, with the existing skip count allowed.

- [ ] **Step 2: Run ruff again**

Run:

```powershell
conda run -n pytorch ruff check app tests
```

Expected: no ruff errors.

- [ ] **Step 3: Inspect final diff**

Run:

```powershell
git diff -- README.md app/static/index.html app/static/styles.css app/static/app.js app/main.py app/orchestration/json_repair.py app/orchestration/orchestrator.py tests/test_llm_tools.py
```

Expected: changes are limited to README, presentation copy/style, and lint cleanup. No API or workflow behavior changes.

## Self-Review

Spec coverage:

- UI presentation polish: Task 2.
- GitHub-style README: Task 1.
- Minimal hygiene and ruff cleanup: Task 3.
- Stable behavior verification: Task 4.
- No orchestrator split: explicitly out of scope and not included in tasks.

Placeholder scan:

- No `TBD`, `TODO`, or open-ended implementation placeholders are present.

Type consistency:

- No new Python APIs, JavaScript APIs, or schemas are introduced.
