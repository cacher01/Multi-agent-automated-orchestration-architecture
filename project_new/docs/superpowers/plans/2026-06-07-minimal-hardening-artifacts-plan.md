# Minimal Hardening and Task Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add practical runtime controls, complete the lightweight Research and ReAct paths, harden unsafe tools, and support task-scoped generated files without disrupting existing workflows.

**Architecture:** Keep orchestration in the existing `Orchestrator`, but add small focused helpers for task-aware LLM accounting and artifact storage. All tools remain centrally registered and executed through `ToolExecutor`; artifact paths are generated server-side and persisted in SQLite.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, SQLite, httpx, pytest.

---

## File Structure

- Create `app/llm/task_client.py`: task-aware LLM wrapper and token accounting.
- Create `app/tools/builtin/artifacts.py`: artifact writer and ZIP archiver.
- Create `app/services/artifact_service.py`: task directory validation and artifact lookup.
- Modify `app/core/config.py`: timeout and artifact settings.
- Modify `app/core/errors.py`: cancellation and timeout exceptions.
- Modify `app/db/database.py`: artifact table.
- Modify `app/db/repositories.py`: token and artifact repository operations.
- Modify `app/schemas/workflow.py`: structured ReAct decision.
- Modify `app/orchestration/prompts.py`: ReAct decision prompt.
- Modify `app/orchestration/orchestrator.py`: checkpoints, Research, ReAct, and optional artifact generation.
- Modify `app/tools/executor.py`: cancellation checkpoint hook.
- Modify `app/tools/builtin/web_fetch.py`: DNS and redirect validation.
- Modify `app/tools/builtin/calculator.py`: expression resource limits.
- Modify `app/main.py`: artifact registration and download endpoints.
- Modify `README.md`: new settings, tools, and API endpoints.
- Add focused tests under `tests/`.

### Task 1: Runtime Cancellation, Timeout, and Token Accounting

**Files:**
- Create: `app/llm/task_client.py`
- Modify: `app/core/config.py`
- Modify: `app/core/errors.py`
- Modify: `app/db/repositories.py`
- Modify: `app/orchestration/orchestrator.py`
- Modify: `app/tools/executor.py`
- Test: `tests/test_runtime_controls.py`

- [ ] **Step 1: Write failing runtime control tests**

```python
def test_task_llm_client_accumulates_response_tokens():
    response = asyncio.run(client.chat([{"role": "user", "content": "x"}]))
    assert response.token_estimate == 17
    assert repo.get_task(task_id)["token_estimate"] == 17


def test_checkpoint_raises_for_cancelled_task():
    repo.update_task_status(task_id, TaskStatus.CANCELLED)
    with pytest.raises(TaskCancelledError):
        orchestrator._checkpoint(task_id)


def test_checkpoint_raises_after_task_timeout():
    settings = Settings(task_timeout_seconds=1)
    repo.set_task_created_at(task_id, old_timestamp)
    with pytest.raises(TaskTimeoutError):
        orchestrator._checkpoint(task_id)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
conda run -n pytorch python -m pytest tests/test_runtime_controls.py -q
```

Expected: failures for missing task-aware client, timeout setting, token increment, and checkpoint behavior.

- [ ] **Step 3: Implement task-aware LLM accounting**

Implement `TaskAwareLLMClient` with this public shape:

```python
class TaskAwareLLMClient:
    def __init__(self, delegate, repository, task_id, checkpoint):
        ...

    async def chat(self, messages, **kwargs):
        self.checkpoint(self.task_id)
        response = await self.delegate.chat(messages, **kwargs)
        self.repository.increment_task_tokens(
            self.task_id, response.token_estimate
        )
        self.checkpoint(self.task_id)
        return response
```

Add an atomic repository update:

```sql
update tasks
set token_estimate = token_estimate + ?, updated_at = ?
where task_id = ?
```

- [ ] **Step 4: Implement cooperative checkpoints**

Add `TASK_TIMEOUT_SECONDS=600` to settings and implement:

```python
def _checkpoint(self, task_id: str) -> None:
    task = self.repository.get_task(task_id)
    if task is None:
        raise ValueError(...)
    if task["status"] == TaskStatus.CANCELLED.value:
        raise TaskCancelledError(task_id)
    if elapsed_seconds(task["created_at"]) > self.settings.task_timeout_seconds:
        raise TaskTimeoutError(task_id)
```

Use the task-aware client for routing, decomposition, workers, evaluations, and final synthesis. Add checkpoints before workflow rounds, DAG layers, tool calls, and final persistence. Handle cancellation without converting it to failure; persist timeout as a clear failure.

- [ ] **Step 5: Run focused and existing cancellation tests**

```powershell
conda run -n pytorch python -m pytest tests/test_runtime_controls.py tests/test_v2_features.py -q
```

Expected: PASS.

### Task 2: Harden `web_fetch` and `calculator`

**Files:**
- Modify: `app/tools/builtin/web_fetch.py`
- Modify: `app/tools/builtin/calculator.py`
- Test: `tests/test_tool_safety.py`
- Test: `tests/test_llm_tools.py`

- [ ] **Step 1: Write failing safety tests**

```python
def test_web_fetch_rejects_hostname_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", private_dns_result)
    assert asyncio.run(is_public_http_url("https://example.test")) is False


def test_web_fetch_revalidates_redirect_target():
    with pytest.raises(ValueError, match="public"):
        asyncio.run(tool.run({"url": "https://public.test/start"}))


@pytest.mark.parametrize("expression", [
    "1" * 201,
    "2 ** 101",
    "(" * 21 + "1" + ")" * 21,
])
def test_calculator_rejects_resource_intensive_expression(expression):
    with pytest.raises(ValueError):
        asyncio.run(CalculatorTool().run({"expression": expression}))
```

- [ ] **Step 2: Verify RED**

```powershell
conda run -n pytorch python -m pytest tests/test_tool_safety.py -q
```

- [ ] **Step 3: Implement URL validation and manual redirects**

Make URL validation asynchronous so hostnames are resolved through
`socket.getaddrinfo`. Reject credentials and every address where
`ipaddress.ip_address(address).is_global` is false.

Use `follow_redirects=False`, resolve `Location` through `urljoin`, validate each
target, and stop after three redirects. Require a textual content type and
truncate the response to configured limits.

- [ ] **Step 4: Implement calculator limits**

Validate source length, count AST nodes, measure recursive depth, bound exponent
magnitude, and reject non-finite or absolute values above `1e100` after every
operation.

- [ ] **Step 5: Run safety tests**

```powershell
conda run -n pytorch python -m pytest tests/test_tool_safety.py tests/test_llm_tools.py -q
```

Expected: PASS.

### Task 3: Complete the Lightweight Research Pipeline

**Files:**
- Modify: `app/orchestration/orchestrator.py`
- Modify: `app/tools/executor.py`
- Modify: `app/tools/builtin/research_tools.py`
- Test: `tests/test_research_pipeline.py`
- Test: `tests/test_v2_quality.py`

- [ ] **Step 1: Write failing Research tests**

Cover:

```python
def test_research_runs_at_least_two_distinct_queries(): ...
def test_research_deduplicates_normalized_urls(): ...
def test_research_fetches_only_top_two_pages(): ...
def test_research_emits_citation_check_event(): ...
def test_research_runs_only_one_supplemental_search(): ...
def test_research_with_no_evidence_fails_clearly(): ...
```

Use local mock tools; do not call external providers.

- [ ] **Step 2: Verify RED**

```powershell
conda run -n pytorch python -m pytest tests/test_research_pipeline.py -q
```

- [ ] **Step 3: Implement search aggregation**

Change `_research_context` to execute at least the first two planned queries,
up to `research_max_queries`. Normalize URLs by lowercasing scheme/host,
removing fragments, and removing trailing `/`. Keep unique results ordered by
search rank and first occurrence.

- [ ] **Step 4: Add safe top-page fetch**

Call `web_fetch` for at most `min(fetch_top_results, 2)` top URLs when registered.
Persist fetched pages as evidence with `source_type="fetched_page"` and append
their summaries to synthesis context. Fetch failure is non-fatal.

- [ ] **Step 5: Connect citation checker, critic, and supplemental search**

Execute `citation_checker` after synthesis and emit
`citation_check_completed`. Execute `result_critic`. If either rejects the
answer, run one supplemental query, add only new evidence, and synthesize once
more. Do not exceed `research_supplemental_searches`.

- [ ] **Step 6: Run Research regressions**

```powershell
conda run -n pytorch python -m pytest tests/test_research_pipeline.py tests/test_v2_features.py tests/test_v2_quality.py -q
```

Expected: PASS.

### Task 4: General Structured ReAct

**Files:**
- Modify: `app/schemas/workflow.py`
- Modify: `app/orchestration/prompts.py`
- Modify: `app/orchestration/orchestrator.py`
- Test: `tests/test_react_workflow.py`
- Test: `tests/test_v2_features.py`

- [ ] **Step 1: Write failing structured ReAct tests**

Create one parameterized test for:

```python
[
    ("weather", {"city": "Beijing"}),
    ("current_time", {"utc_offset": "+08:00"}),
    ("date_calculator", {"base_date": "2026-06-07", "days": 3}),
    ("unit_converter", {"value": 2, "source_unit": "km", "target_unit": "m"}),
    ("calculator", {"expression": "2 + 3 * 4"}),
]
```

Also test:

- disallowed tool selection;
- unavailable tool selection;
- five-call limit;
- deterministic weather/time fallback after parse failure.

- [ ] **Step 2: Verify RED**

```powershell
conda run -n pytorch python -m pytest tests/test_react_workflow.py -q
```

- [ ] **Step 3: Add schema and prompt**

```python
class ReactDecision(BaseModel):
    action: Literal["tool_call", "final_answer"]
    tool_name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str
    answer: str = ""
```

The prompt must return only this JSON shape and may select only the five
functional tools listed in the design.

- [ ] **Step 4: Implement bounded ReAct loop**

Pass tool names, descriptions, user task, and prior observations to each
decision call. Validate the tool against the fixed allowlist and registry,
execute centrally, and append the result. Finish with normal final synthesis.
On repeated parse failure, call the existing deterministic fallback.

- [ ] **Step 5: Run ReAct regressions**

```powershell
conda run -n pytorch python -m pytest tests/test_react_workflow.py tests/test_v2_features.py -q
```

Expected: PASS.

### Task 5: Artifact Persistence and Safe File Tools

**Files:**
- Create: `app/services/artifact_service.py`
- Create: `app/tools/builtin/artifacts.py`
- Modify: `app/core/config.py`
- Modify: `app/db/database.py`
- Modify: `app/db/repositories.py`
- Modify: `app/main.py`
- Test: `tests/test_artifact_tools.py`

- [ ] **Step 1: Write failing artifact tests**

Cover:

```python
def test_writer_creates_markdown_inside_task_directory(): ...
def test_writer_serializes_json_and_csv_structurally(): ...
def test_writer_rejects_absolute_traversal_hidden_and_device_names(): ...
def test_writer_never_overwrites_existing_file(): ...
def test_writer_enforces_count_and_size_limits(): ...
def test_archiver_contains_only_same_task_non_zip_artifacts(): ...
def test_archiver_rejects_cross_task_artifacts(): ...
```

Use `tmp_path` as the artifact root.

- [ ] **Step 2: Verify RED**

```powershell
conda run -n pytorch python -m pytest tests/test_artifact_tools.py -q
```

- [ ] **Step 3: Add artifact table and repository operations**

Create:

```sql
create table if not exists artifacts (
    artifact_id text primary key,
    task_id text not null,
    filename text not null,
    media_type text not null,
    size_bytes integer not null,
    relative_path text not null,
    created_at text not null
);
```

Implement registration, task-scoped lookup, listing, count, and total-size
queries.

- [ ] **Step 4: Implement `ArtifactService`**

Resolve all files under `artifact_root/<task_id>`. Validate safe base filenames,
reject symlinks, choose non-conflicting names such as `report-2.md`, and verify
resolved paths remain under the task directory.

- [ ] **Step 5: Implement writer and archiver tools**

Use `json.dump` for JSON, `csv.DictWriter` for CSV, and `zipfile.ZipFile` for
archives. Register metadata only after the file is successfully closed and
measured. Remove partial output when serialization fails.

- [ ] **Step 6: Run artifact tool tests**

```powershell
conda run -n pytorch python -m pytest tests/test_artifact_tools.py -q
```

Expected: PASS.

### Task 6: Artifact API and Orchestrator Integration

**Files:**
- Modify: `app/main.py`
- Modify: `app/orchestration/orchestrator.py`
- Modify: `app/services/task_service.py`
- Modify: `app/static/app.js`
- Test: `tests/test_artifact_api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

```python
def test_list_task_artifacts_returns_only_same_task(): ...
def test_download_artifact_returns_attachment(): ...
def test_download_rejects_artifact_from_another_task(): ...
def test_download_rejects_missing_or_escaped_file(): ...
```

- [ ] **Step 2: Verify RED**

```powershell
conda run -n pytorch python -m pytest tests/test_artifact_api.py -q
```

- [ ] **Step 3: Add list and download endpoints**

Use task-scoped repository lookup and `FileResponse`. The client supplies only
`task_id` and `artifact_id`; never accept a path. Return 404 for cross-task or
missing artifacts and reject any resolved path outside the configured root.

- [ ] **Step 4: Add explicit artifact request integration**

After textual synthesis, detect explicit requests containing report/file/export/
CSV/JSON/archive terms in Chinese or English. Call `artifact_writer` with the
final answer; call `artifact_archiver` only when archive/ZIP is requested.
Artifact failure sets degraded status and adds a limitation but preserves the
answer.

- [ ] **Step 5: Add minimal UI artifact links**

When a task reaches a terminal state, fetch `/tasks/{task_id}/artifacts`. Render
plain download links below the final result only when artifacts exist. Do not
change the current layout or visualization.

- [ ] **Step 6: Run API and UI regressions**

```powershell
conda run -n pytorch python -m pytest tests/test_artifact_api.py tests/test_api.py tests/test_markdown_ui.py -q
```

Expected: PASS.

### Task 7: Documentation and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-06-07-minimal-hardening-artifacts-plan.md`

- [ ] **Step 1: Update README**

Document:

- `TASK_TIMEOUT_SECONDS`;
- `ARTIFACT_ROOT`;
- supported artifact formats and limits;
- Research and ReAct behavior;
- artifact list and download endpoints;
- the task-scoped filesystem safety boundary.

- [ ] **Step 2: Run the full test suite**

```powershell
conda run -n pytorch python -m pytest
```

Expected: all tests pass.

- [ ] **Step 3: Run compilation**

```powershell
conda run -n pytorch python -m compileall -q app tests
```

Expected: exit code 0.

- [ ] **Step 4: Verify application import**

```powershell
conda run -n pytorch python -c "from app.main import create_app; app=create_app(testing=True); print(app.title, len(app.routes))"
```

Expected: application title and a non-zero route count.

- [ ] **Step 5: Review final diff**

```powershell
git diff --check
git status --short
```

Confirm no secrets, database files, generated artifacts, or unrelated project
files are included.
