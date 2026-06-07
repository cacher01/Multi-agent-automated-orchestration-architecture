# Runtime, Research, and ReAct Hardening Design

## 1. Purpose

This change closes the highest-priority gaps found in the Version 2 review:

- cancellation must stop orchestration after the current blocking call returns;
- task timeout, step count, tool calls, and token estimates must be observable and enforced;
- the research workflow must use the registered research tools as one coherent pipeline;
- ReAct must select every supported read-only functional tool through structured LLM decisions;
- `web_fetch` and `calculator` must resist unsafe or resource-intensive inputs.

The implementation must preserve the existing FastAPI API, SQLite persistence, event stream, replay format, task-scoped sub-agents, and current UI behavior.

## 2. Scope

Included:

- runtime cancellation checkpoints;
- tracked background task lifecycle;
- task-level runtime budget state;
- token usage accumulation from every LLM call;
- task timeout and step/tool/token guardrails;
- complete research pipeline;
- general read-only ReAct loop;
- DNS- and redirect-aware public URL validation;
- calculator complexity limits;
- focused regression and integration tests.

Excluded:

- UI redesign;
- authentication or multi-user ownership;
- shell, file-write, download, browser automation, or code execution tools;
- cross-task long-term memory;
- Go implementation;
- broad refactoring unrelated to the reviewed gaps.

## 3. Runtime Control Architecture

Add a task-scoped `RuntimeController` owned by the Orchestrator. It provides:

- `checkpoint(task_id, step_name)` to reject cancelled, timed-out, or exhausted tasks;
- elapsed-time tracking from task start;
- step accounting;
- token accounting;
- a terminal reason suitable for events and degraded results.

The controller reads cancellation from the repository so API cancellation remains the source of truth. Checkpoints occur:

- after routing;
- before and after every LLM operation;
- before every tool call;
- before each Supervisor or Swarm round;
- before each DAG layer;
- before final synthesis and persistence.

An in-flight HTTP call is not forcibly interrupted. After it returns, its result is discarded if the next checkpoint detects cancellation.

`TaskService` keeps references to background `asyncio.Task` objects by task ID. Completed tasks are removed through a done callback. Unexpected background exceptions are consumed by the callback because the Orchestrator has already persisted the failure state.

## 4. Budget Model

Add these settings with conservative defaults:

- `TASK_TIMEOUT_SECONDS=600`;
- `MAX_TASK_STEPS=40`;
- `MAX_TASK_TOKENS=100000`.

Existing limits remain:

- global tool call limit;
- ReAct tool call limit;
- agent and concurrency limits;
- Swarm round limit.

Every LLM response contributes its `token_estimate` to the task record. The repository exposes an atomic increment operation. Token counts are observability estimates, not billing values.

Budget behavior:

- cancellation produces `cancelled` and never writes a final result;
- timeout or token/step exhaustion before usable intermediate data produces `failed`;
- exhaustion after usable evidence or worker output produces a degraded synthesis without further LLM calls;
- a budget event records the limit, current value, and stopping reason.

The first implementation may use a deterministic fallback renderer for degraded completion.

## 5. LLM Accounting Boundary

Introduce a task-aware LLM wrapper rather than modifying every workflow call manually. The wrapper:

- delegates to the configured LLM client;
- performs a runtime checkpoint before and after the request;
- increments the task token estimate after a successful response;
- preserves the existing `LLMClient` protocol.

The Orchestrator and `AgentRuntime` receive this task-aware client for the duration of a task. Structured-output repair and retry calls are therefore counted automatically.

## 6. Research Pipeline

The research workflow becomes:

1. create 3 to 5 planned queries;
2. run multiple Tavily searches, up to the configured query limit;
3. deduplicate results by normalized URL;
4. rank results deterministically using search rank, query coverage, and source diversity;
5. persist search evidence;
6. fetch up to `research_auto_fetch_pages` top safe URLs;
7. persist fetched-page evidence separately from search snippets;
8. synthesize from persisted evidence;
9. run `citation_checker`;
10. run `result_critic`;
11. perform at most one supplemental search if citations are insufficient or the critic requests revision;
12. synthesize once more only when supplemental evidence was added.

Search and fetch failures are isolated. A failed fetch does not discard its search evidence.

The workflow returns:

- `completed` when synthesis, citations, and critic checks are acceptable;
- `degraded` when usable evidence exists but checking, fetching, or final synthesis is incomplete;
- `failed` only when no usable evidence exists or runtime limits prevent any meaningful result.

`citation_checker` must emit `citation_check_completed`. Critic results influence task status; they are no longer observability-only.

## 7. General ReAct Loop

Add structured models:

- `ReactDecision` with action `tool_call` or `final_answer`;
- tool name;
- validated argument object;
- reasoning summary intended for events, not hidden chain-of-thought;
- optional final answer.

Loop behavior:

1. provide the user task, supported tool specifications, and prior tool observations to the LLM;
2. parse one structured decision;
3. validate the selected tool against the ReAct allowlist;
4. execute centrally through `ToolExecutor`;
5. append the result as an observation;
6. repeat until `final_answer` or five tool calls;
7. use normal final synthesis to produce the stored result.

Allowed tools:

- `weather`;
- `current_time`;
- `date_calculator`;
- `unit_converter`;
- `calculator`.

If structured decisions repeatedly fail, use the existing deterministic weather/time detection as a fallback. A missing requested tool produces a degraded answer with a clear limitation rather than an unrelated tool call.

## 8. Tool Safety

### Web Fetch

For every initial URL and redirect target:

- allow only `http` and `https`;
- reject embedded credentials;
- resolve the hostname;
- reject loopback, private, link-local, multicast, reserved, unspecified, and non-global addresses;
- disable automatic redirects and follow at most three redirects manually;
- reject redirects without a valid `Location`;
- accept only textual response content;
- enforce a response byte limit while streaming;
- decode and truncate to `max_fetch_chars`.

DNS resolution failures reject the URL. This does not fully eliminate DNS rebinding, but validating each target and connecting immediately substantially narrows the prototype risk.

### Calculator

Reject:

- expressions longer than 200 characters;
- ASTs deeper than 20 levels or larger than 100 nodes;
- non-finite numbers;
- exponent magnitude above 100;
- intermediate or final absolute values above `1e100`.

Supported operators remain addition, subtraction, multiplication, division, exponentiation, and unary signs.

## 9. Persistence and Events

Reuse the existing tables and add only repository operations where possible.

Persist:

- cumulative task token estimate;
- budget exhaustion reason in `error_summary`;
- tool calls and evidence as today;
- citation and critic events;
- cancellation and terminal task events.

Add event types:

- `budget_updated`;
- `budget_exhausted`;
- `react_decision`;
- `research_supplemental_started`.

Replay remains backward compatible because event payloads are additive.

## 10. Error Handling

- Cancellation is not converted to failure.
- Known budget exhaustion is handled separately from unexpected exceptions.
- Tool validation failures are persisted as failed tool calls.
- One failed Supervisor worker does not fail unrelated workers.
- Research network failures preserve successful evidence and return degraded output when possible.
- Background task exceptions must be observed and must not produce unhandled-task warnings.

## 11. Testing

Tests must cover:

- cancellation after an in-flight LLM or tool call;
- cancellation checks in Supervisor, DAG, and Swarm loops;
- background task tracking and cleanup;
- token accumulation across structured-output repair calls;
- timeout, step, tool, and token exhaustion;
- degraded completion with existing evidence;
- research multi-query, deduplication, fetch, citation check, critic, and supplemental search limits;
- ReAct selection of all five functional tools;
- disallowed or unavailable ReAct tools;
- private DNS results and unsafe redirects in `web_fetch`;
- oversized, deeply nested, and excessive exponent calculator expressions;
- replay and existing API compatibility.

The full test suite, Python compilation, and FastAPI import check must pass before completion.

## 12. Acceptance Criteria

The change is complete when:

- cancelling a running task prevents additional workflow layers and final result persistence;
- task token estimates become non-zero after real or mocked LLM calls;
- every configured runtime limit has an enforced code path and test;
- research uses multiple searches, safe fetches, citation checking, and at most one supplemental pass;
- ReAct can invoke every registered functional tool through structured decisions;
- unsafe fetch targets and pathological calculator inputs are rejected;
- replay continues to expose task, events, agents, tool calls, evidence, and result;
- all automated verification commands pass.
