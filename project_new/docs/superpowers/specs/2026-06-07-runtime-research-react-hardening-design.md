# Minimal Runtime, Tool, and Research Hardening Design

## 1. Purpose

This change improves the current Shannon-inspired prototype without turning it
into a production-scale orchestration platform. It keeps the existing API,
SQLite database, workflows, replay model, and UI behavior stable.

The implementation focuses on:

- practical cancellation checkpoints;
- basic timeout and token observability;
- a useful research pipeline;
- structured selection of existing functional tools;
- safe web fetch and calculator limits;
- task-scoped report creation and archive generation.

## 2. Scope

Included:

- cancellation checks between workflow steps, tool calls, agent rounds, and DAG
  layers;
- task timeout;
- task-level token estimate accumulation;
- existing tool-call limits;
- multi-query research with deduplication;
- fetching up to two safe pages;
- citation checking and at most one supplemental search;
- structured ReAct decisions for the five existing functional tools;
- `artifact_writer` for Markdown, text, JSON, and CSV;
- `artifact_archiver` for ZIP creation;
- artifact listing and controlled download;
- focused regression tests.

Excluded:

- a general workflow engine rewrite;
- complex budget degradation algorithms;
- model fallback;
- Supervisor supplemental worker rounds;
- a complete step executor for `plan_execute`;
- arbitrary filesystem access;
- shell or code execution;
- remote file download;
- cross-task memory;
- authentication and multi-user isolation;
- UI redesign.

## 3. Runtime Control

The Orchestrator uses small repository-backed checks rather than a new runtime
subsystem.

Add:

- `TASK_TIMEOUT_SECONDS`, default `600`;
- a task start-time check based on persisted timestamps;
- `checkpoint(task_id)` in the Orchestrator;
- repository token increment support.

Checkpoints run:

- after routing;
- before and after tool calls;
- before Supervisor and Swarm rounds;
- before each DAG layer;
- before final synthesis and result persistence.

Cancellation remains cooperative. An in-flight HTTP or LLM request may finish,
but its output must not start another workflow step or persist a final result.

Every successful LLM response increments `tasks.token_estimate`. Token estimates
are for visibility only in this phase; there is no token hard stop.

## 4. Research Workflow

The research flow is:

1. create up to five queries;
2. execute at least two distinct queries when available;
3. deduplicate results by normalized URL;
4. keep the highest-ranked configured number of results;
5. fetch up to two top public pages through `web_fetch`;
6. include fetched text and search snippets in synthesis context;
7. run `citation_checker`;
8. run `result_critic`;
9. perform at most one supplemental search when citations are invalid or the
   critic rejects the answer;
10. return completed or degraded output from persisted evidence.

Search and fetch failures are isolated. A failed fetch does not remove its
search-result evidence. No evidence produces a clear task failure.

## 5. ReAct Workflow

Add a structured `ReactDecision`:

- `action`: `tool_call` or `final_answer`;
- `tool_name`;
- `arguments`;
- `summary`;
- optional `answer`.

The Orchestrator presents the available functional tools and previous
observations to the LLM. It validates the decision, executes the requested tool
centrally, records the observation, and repeats up to five tool calls.

Allowed tools:

- `weather`;
- `current_time`;
- `date_calculator`;
- `unit_converter`;
- `calculator`.

The existing deterministic weather/time behavior remains as fallback when a
structured decision cannot be parsed. Missing or disallowed tools produce a
degraded answer with a limitation.

## 6. Task Artifact Tools

Artifacts are stored only below:

```text
artifacts/<task_id>/
```

### Artifact Writer

`artifact_writer` creates one new file for the current task.

Supported formats:

- `.md`;
- `.txt`;
- `.json`;
- `.csv`.

Inputs:

- requested filename;
- format;
- content;
- optional structured rows for JSON or CSV.

Rules:

- reject absolute paths, directory separators, `..`, device names, and hidden
  filenames;
- sanitize the base filename;
- never overwrite an existing file;
- maximum 10 artifacts per task;
- maximum 1 MiB per artifact;
- use UTF-8;
- JSON and CSV are serialized using standard-library writers rather than string
  concatenation.

### Artifact Archiver

`artifact_archiver` creates a ZIP containing the current task's generated
artifacts.

Rules:

- include only files already registered for the same task;
- do not include an existing ZIP in another ZIP;
- maximum uncompressed input size 5 MiB;
- never overwrite an existing archive;
- archive members use safe base filenames only.

Artifacts are not visible to sub-agents unless the Orchestrator explicitly
passes their metadata. Tools cannot read arbitrary local files.

## 7. Artifact Persistence and API

Add an `artifacts` table:

- `artifact_id`;
- `task_id`;
- `filename`;
- `media_type`;
- `size_bytes`;
- `relative_path`;
- `created_at`.

Repository methods:

- register artifact;
- list artifacts for task;
- get artifact by task and artifact ID;
- count and total artifact size.

API:

- `GET /tasks/{task_id}/artifacts`;
- `GET /tasks/{task_id}/artifacts/{artifact_id}`.

The download endpoint:

- looks up the artifact by both task ID and artifact ID;
- resolves the stored path under the configured artifact root;
- rejects missing files and any path escaping the task directory;
- returns `Content-Disposition: attachment`;
- never accepts a filesystem path from the client.

Artifact operations are persisted as normal tool calls and emitted in the
existing event stream.

## 8. Tool Invocation Policy

Artifact tools are centrally registered and executed through `ToolExecutor`.

They may be selected only when the user explicitly requests an output file,
report, table export, JSON export, CSV export, or archive. They are not part of
the normal ReAct allowlist.

The Orchestrator may call them after final content has been produced. A failed
artifact operation degrades the task but does not discard the textual answer.

No tool may:

- access another task directory;
- access source files, `.env`, or the database;
- execute generated content;
- create executable file formats;
- follow symbolic links.

## 9. Tool Safety

### Web Fetch

- only `http` and `https`;
- reject embedded credentials;
- resolve hostnames and reject non-global IP addresses;
- disable automatic redirects;
- validate each redirect target;
- follow at most three redirects;
- accept textual content only;
- enforce response and decoded text limits.

### Calculator

- maximum expression length: 200 characters;
- maximum AST nodes: 100;
- maximum nesting depth: 20;
- maximum exponent magnitude: 100;
- reject non-finite or absolute values above `1e100`.

## 10. Testing

Tests cover:

- cancellation between workflow stages;
- timeout detection;
- token estimate accumulation;
- research multi-query, deduplication, fetch, citation check, and supplemental
  search limit;
- all five ReAct tools and disallowed tool selection;
- private DNS results and unsafe redirects;
- pathological calculator inputs;
- artifact path traversal, overwrite, count, and size limits;
- JSON and CSV serialization;
- cross-task artifact access rejection;
- archive contents;
- artifact list and download endpoints;
- existing replay and API compatibility.

Before completion:

- the full Pytest suite passes;
- `python -m compileall -q app tests` passes;
- FastAPI application import passes.

## 11. Acceptance Criteria

The implementation is complete when:

- cancellation prevents additional workflow stages and final persistence;
- token estimates are stored for LLM-backed tasks;
- research performs multiple searches and uses safe fetched evidence;
- ReAct can select all existing functional tools;
- unsafe fetch and calculator inputs are rejected;
- a user can request a report or CSV, see it in the task artifact list, and
  download it;
- generated files cannot escape their task directory or overwrite existing
  files;
- existing workflows, sessions, replay, Markdown output, and UI remain
  functional.
