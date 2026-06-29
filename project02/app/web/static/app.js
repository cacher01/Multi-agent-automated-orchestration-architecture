const form = document.querySelector("#taskForm");
const taskInput = document.querySelector("#taskInput");
const chatHistory = document.querySelector("#chatHistory");
const summary = document.querySelector("#summary");
const statusBadge = document.querySelector("#statusBadge");
const currentTaskLabel = document.querySelector("#currentTaskLabel");
const memoryPanel = document.querySelector("#memoryPanel");
const memoryList = document.querySelector("#memoryList");
const stateTree = document.querySelector("#stateTree");
const taskArchive = document.querySelector("#taskArchive");
const persistLogs = document.querySelector("#persistLogs");
const persistIntermediate = document.querySelector("#persistIntermediate");
const newSessionButton = document.querySelector("#newSessionButton");

const tasks = new Map();
let currentSessionId = newSessionId();
let activeTaskId = null;
let selectedTaskId = null;
let pollTimer = null;
let taskSequence = 0;

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = taskInput.value.trim();
  if (!input) return;

  appendMessage("user", "You", input);
  taskInput.value = "";
  setBusy("Submitting");

  const placeholder = appendMessage("assistant", "Main Agent", "处理中...");
  const payload = {
    input,
    session_id: currentSessionId,
    persist_logs: persistLogs.checked,
    persist_intermediate_results: persistIntermediate.checked,
  };

  try {
    const response = await fetch("/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail?.message || "Request failed");
    }
    activeTaskId = data.task_id;
    selectedTaskId = data.task_id;
    currentSessionId = data.session_id || currentSessionId;
    registerTask(data, input);
    renderResponse(data, placeholder);
    await refreshLogs(data.task_id);
    renderArchive();
    startPolling(data);
  } catch (error) {
    renderError(error, placeholder);
  }
});

newSessionButton.addEventListener("click", () => {
  currentSessionId = newSessionId();
  activeTaskId = null;
  selectedTaskId = null;
  stopPolling();
  appendMessage("assistant", "System", "已开始新会话。");
  renderSummary({});
  renderStateTree(null);
  renderArchive();
  setBusy("Ready");
});

taskInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

async function refreshResult(taskId = activeTaskId) {
  if (!taskId) return null;
  const response = await fetch(`/tasks/${encodeURIComponent(taskId)}/result`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail?.message || "Result query failed");
  }
  return data;
}

async function refreshLogs(taskId = selectedTaskId) {
  if (!taskId) return;
  try {
    const response = await fetch(`/tasks/${encodeURIComponent(taskId)}/logs`);
    const data = await response.json();
    if (!response.ok) return;
    updateTask(taskId, { events: data.events || [] });
    if (selectedTaskId === taskId) renderStateTree(taskId);
    renderArchive();
  } catch (_error) {
    // Log polling is observational and should not interrupt the chat flow.
  }
}

function startPolling(initialData) {
  stopPolling();
  const status = initialData.status;
  if (!["running", "created", "planning"].includes(status)) return;

  pollTimer = window.setInterval(async () => {
    try {
      const taskId = activeTaskId;
      const data = await refreshResult(taskId);
      await refreshLogs(taskId);
      if (data) {
        updateTask(data.task_id, {
          status: data.status,
          mode: data.mode || data.execution_mode,
          result: data.result,
          failure: data.failure,
        });
        if (selectedTaskId === data.task_id) renderSummary(data);
      }
      if (data && !["running", "created", "planning"].includes(data.status)) {
        stopPolling();
        appendMessage("assistant", "Main Agent", formatResponse(data));
        renderMemories(data.candidate_memories || []);
        setBusy(data.status || "Done");
        renderArchive();
      }
    } catch (error) {
      stopPolling();
      appendMessage("assistant", "Main Agent", `查询任务结果失败：${error.message}`);
      setBusy("Error");
    }
  }, 1200);
}

function stopPolling() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function updateMemory(memoryId, action) {
  setBusy("Saving");
  try {
    const response = await fetch(`/memories/${encodeURIComponent(memoryId)}/${action}`, { method: "POST" });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail?.message || "Memory update failed");
    }
    await refreshLogs();
    setBusy("Saved");
  } catch (error) {
    appendMessage("assistant", "System", error.message);
    setBusy("Error");
  }
}

function renderResponse(data, messageElement) {
  const target = messageElement || appendMessage("assistant", "Main Agent", "");
  setMessageBody(target, formatResponse(data));
  updateTask(data.task_id, {
    status: data.status,
    mode: data.mode || data.execution_mode,
    result: data.result,
    failure: data.failure,
  });
  renderSummary(data);
  renderStateTree(data.task_id);
  renderMemories(data.candidate_memories || []);
  setBusy(data.status || "Done");
}

function formatResponse(data) {
  if (data.result) return data.result;
  if (data.tool_message) return data.tool_message;
  if (data.clarification_question) return `需要补充信息：${data.clarification_question}`;
  if (data.failure) return `任务失败：${data.failure.error_message || data.failure.reason}`;
  if (data.status === "running") return `任务已进入异步执行，Task ID: ${data.task_id}`;
  return JSON.stringify(data, null, 2);
}

function renderSummary(data) {
  currentTaskLabel.textContent = data.task_id ? shortId(data.task_id) : "暂无任务";
  summary.replaceChildren();
  addSummary("Task ID", data.task_id);
  addSummary("Status", data.status);
  addSummary("Mode", data.mode || data.execution_mode);
  addSummary("Retry", data.retry_count);
}

function renderStateTree(taskId) {
  selectedTaskId = taskId;
  const task = tasks.get(taskId);
  stateTree.replaceChildren();
  stateTree.classList.toggle("empty", !task);
  if (!task) {
    stateTree.textContent = "暂无运行状态。";
    return;
  }

  for (const group of buildStateGroups(task)) {
    const details = document.createElement("details");
    details.className = `tree-node ${group.status}`;
    details.open = group.open;

    const summaryNode = document.createElement("summary");
    const dot = document.createElement("span");
    dot.className = "tree-dot";
    const title = document.createElement("span");
    title.className = "tree-title";
    title.textContent = group.title;
    const count = document.createElement("span");
    count.className = "tree-count";
    count.textContent = group.events.length ? `${group.events.length}` : "";
    summaryNode.append(dot, title, count);
    details.append(summaryNode);

    const body = document.createElement("div");
    body.className = "tree-detail";
    if (group.events.length === 0) {
      body.textContent = group.emptyText;
    } else {
      for (const event of group.events) {
        body.append(renderEvent(event));
      }
    }
    details.append(body);
    stateTree.append(details);
  }
}

function buildStateGroups(task) {
  const events = task.events || [];
  const byType = (types) => events.filter((event) => types.includes(event.event_type));
  return [
    {
      title: "任务接收",
      status: statusFor(byType(["task_created"]), task.status),
      open: false,
      emptyText: "尚未创建任务。",
      events: byType(["task_created"]),
    },
    {
      title: "决策与规划",
      status: statusFor(byType(["decision_made", "orchestrator_routed", "plan_created"]), task.status),
      open: task.status === "running",
      emptyText: "等待决策与计划。",
      events: byType(["decision_made", "orchestrator_routed", "plan_created"]),
    },
    {
      title: "Agent 执行",
      status: statusFor(byType(["step_started", "agent_invoked", "step_completed"]), task.status),
      open: task.status === "running",
      emptyText: "尚未调用子 Agent。",
      events: byType(["step_started", "agent_invoked", "step_completed"]),
    },
    {
      title: "工具调用",
      status: statusFor(byType(["tool_requested", "tool_completed", "tool_failed"]), task.status),
      open: false,
      emptyText: "当前任务没有工具调用。",
      events: byType(["tool_requested", "tool_completed", "tool_failed"]),
    },
    {
      title: "聚合与验收",
      status: statusFor(byType(["result_aggregated", "review_completed", "orchestrator_finalized"]), task.status),
      open: task.status === "succeeded",
      emptyText: "等待结果聚合。",
      events: byType(["result_aggregated", "review_completed", "orchestrator_finalized"]),
    },
    {
      title: "完成状态",
      status: terminalStatus(task.status),
      open: ["failed", "succeeded", "waiting_for_clarification"].includes(task.status),
      emptyText: "任务尚未结束。",
      events: byType(["task_succeeded", "task_failed", "clarification_requested"]),
    },
  ];
}

function statusFor(events, taskStatus) {
  if (events.some((event) => event.event_type.includes("failed"))) return "failed";
  if (events.length > 0) return "done";
  if (["running", "planning", "created"].includes(taskStatus)) return "pending";
  return "idle";
}

function terminalStatus(status) {
  if (status === "succeeded") return "done";
  if (["failed", "timeout", "budget_exceeded", "permission_denied"].includes(status)) return "failed";
  if (status === "waiting_for_clarification") return "pending";
  return "idle";
}

function renderEvent(event) {
  const item = document.createElement("details");
  item.className = "event-node";
  const header = document.createElement("summary");
  const type = document.createElement("span");
  type.textContent = labelEvent(event.event_type);
  const time = document.createElement("time");
  time.textContent = formatTime(event.created_at);
  header.append(type, time);
  const payload = document.createElement("pre");
  payload.textContent = JSON.stringify(event.payload || {}, null, 2);
  item.append(header, payload);
  return item;
}

function renderArchive() {
  taskArchive.replaceChildren();
  const archived = [...tasks.values()]
    .filter((task) => task.task_id !== selectedTaskId)
    .sort((left, right) => left.sequence - right.sequence);
  taskArchive.classList.toggle("empty", archived.length === 0);
  if (archived.length === 0) {
    taskArchive.textContent = "暂无历史任务。";
    return;
  }
  for (const task of archived) {
    const item = document.createElement("details");
    item.className = "archive-item";
    const header = document.createElement("summary");
    const title = document.createElement("span");
    const shortInput = task.input.length > 24 ? `${task.input.slice(0, 24)}...` : task.input;
    title.textContent = `${task.sequence}. ${shortInput}`;
    const status = document.createElement("span");
    status.className = `archive-status ${terminalStatus(task.status)}`;
    status.textContent = task.status;
    header.append(title, status);
    const body = document.createElement("div");
    body.className = "archive-body";
    body.append(infoLine("Task ID", task.task_id), infoLine("Mode", task.mode || "-"), infoLine("Events", String((task.events || []).length)));
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "查看状态图";
    button.addEventListener("click", async () => {
      selectedTaskId = task.task_id;
      renderSummary(task);
      await refreshLogs(task.task_id);
      renderStateTree(task.task_id);
      renderArchive();
    });
    body.append(button);
    item.append(header, body);
    taskArchive.append(item);
  }
}

function renderMemories(memories) {
  memoryList.replaceChildren();
  memoryPanel.classList.toggle("hidden", memories.length === 0);
  for (const memory of memories) {
    const item = document.createElement("div");
    item.className = "memory-item";
    const text = document.createElement("div");
    text.textContent = memory.content;
    const actions = document.createElement("div");
    actions.className = "memory-actions";
    const approve = document.createElement("button");
    approve.type = "button";
    approve.textContent = "Approve";
    approve.addEventListener("click", () => updateMemory(memory.memory_id, "approve"));
    const reject = document.createElement("button");
    reject.type = "button";
    reject.textContent = "Reject";
    reject.addEventListener("click", () => updateMemory(memory.memory_id, "reject"));
    actions.append(approve, reject);
    item.append(text, actions);
    memoryList.append(item);
  }
}

function appendMessage(kind, label, text) {
  const message = document.createElement("article");
  message.className = `message ${kind}`;
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = label;
  const body = document.createElement("div");
  body.className = "message-body";
  message.append(meta, body);
  chatHistory.append(message);
  setMessageBody(message, text);
  chatHistory.scrollTop = chatHistory.scrollHeight;
  return message;
}

function setMessageBody(messageElement, text) {
  const body = messageElement.querySelector(".message-body");
  body.innerHTML = renderMarkdownLite(text || "");
}

function renderMarkdownLite(text) {
  const escaped = escapeHtml(text);
  return escaped
    .replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>")
    .replace(/^### (.*)$/gm, "<h3>$1</h3>")
    .replace(/^## (.*)$/gm, "<h2>$1</h2>")
    .replace(/^# (.*)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/^\s*[-*] (.*)$/gm, "<div class=\"md-list-item\">• $1</div>")
    .replace(/\n/g, "<br />");
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function registerTask(data, input) {
  taskSequence += 1;
  tasks.set(data.task_id, {
    task_id: data.task_id,
    session_id: data.session_id || currentSessionId,
    sequence: taskSequence,
    input,
    status: data.status,
    mode: data.mode || data.execution_mode,
    result: data.result || null,
    failure: data.failure || null,
    events: [],
    created_at: new Date().toISOString(),
  });
}

function updateTask(taskId, patch) {
  if (!taskId) return;
  const current = tasks.get(taskId) || { task_id: taskId, input: "", events: [] };
  tasks.set(taskId, { ...current, ...patch });
}

function addSummary(label, value) {
  if (value === undefined || value === null) return;
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = value;
  summary.append(dt, dd);
}

function infoLine(label, value) {
  const line = document.createElement("div");
  line.className = "info-line";
  const key = document.createElement("span");
  key.textContent = label;
  const val = document.createElement("span");
  val.textContent = value;
  line.append(key, val);
  return line;
}

function renderError(error, messageElement) {
  const target = messageElement || appendMessage("assistant", "System", "");
  setMessageBody(target, error.message);
  setBusy("Error");
}

function setBusy(label) {
  statusBadge.textContent = label;
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString();
}

function shortId(value) {
  return value ? value.replace("task_", "").slice(0, 8) : "";
}

function newSessionId() {
  return `session_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function labelEvent(type) {
  const labels = {
    task_created: "任务创建",
    decision_made: "决策判断",
    orchestrator_routed: "编排路由",
    plan_created: "计划生成",
    step_started: "步骤开始",
    agent_invoked: "Agent 调用",
    step_completed: "步骤完成",
    tool_requested: "工具请求",
    tool_completed: "工具完成",
    tool_failed: "工具失败",
    result_aggregated: "结果聚合",
    review_completed: "验收完成",
    orchestrator_finalized: "主 Agent 综合",
    clarification_requested: "请求澄清",
    task_succeeded: "任务成功",
    task_failed: "任务失败",
    retry_started: "重试开始",
    execution_failed: "执行失败",
  };
  return labels[type] || type;
}
