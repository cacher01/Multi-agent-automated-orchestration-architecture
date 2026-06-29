(function () {
  const $ = (id) => document.getElementById(id);
  const form = $("taskForm");
  const input = $("questionInput");
  const submitButton = $("submitButton");
  const cancelButton = $("cancelButton");
  const artifactsEl = $("artifacts");
  const statusEl = $("taskStatus");
  const taskIdEl = $("taskId");
  const workflowEl = $("workflowLabel");
  const stageTitleEl = $("stageTitle");
  const eventCountEl = $("eventCount");
  const agentCountEl = $("agentCount");
  const toolCountEl = $("toolCount");
  const eventsEl = $("eventStream");
  const pathEl = $("eventPath");
  const graphEl = $("executionTree");
  const graphEmptyEl = $("treeEmpty");
  const selectedEventEl = $("selectedEvent");
  const answerEl = $("finalAnswer");
  const citationsEl = $("citations");
  const detailsEl = $("executionDetails");
  const confidenceEl = $("confidenceLabel");

  let source = null;
  let activeTaskId = null;
  let resultFetched = false;
  let eventRecords = [];
  let graphNodes = new Map();
  let graphEdges = new Map();
  let agentCount = 0;
  let toolCount = 0;
  let activeSessionId = "";
  const terminalStatuses = new Set(["completed", "degraded", "failed", "cancelled"]);

  function setStatus(value) {
    const status = value || "Unknown";
    statusEl.textContent = status;
    statusEl.dataset.state = status.toLowerCase();
  }

  function resetView(question) {
    if (source) source.close();
    source = null;
    activeTaskId = null;
    resultFetched = false;
    eventRecords = [];
    graphNodes = new Map();
    graphEdges = new Map();
    agentCount = 0;
    toolCount = 0;
    setStatus("Submitting");
    taskIdEl.textContent = "Creating task";
    workflowEl.textContent = "Pending";
    stageTitleEl.textContent = question.length > 54 ? `${question.slice(0, 54)}...` : question;
    eventCountEl.textContent = "0";
    agentCountEl.textContent = "0";
    toolCountEl.textContent = "0";
    eventsEl.innerHTML = "";
    pathEl.innerHTML = "";
    graphEl.innerHTML = "";
    graphEmptyEl.hidden = false;
    selectedEventEl.textContent = "Select a graph node or event.";
    cancelButton.disabled = true;
    answerEl.textContent = "Task is running...";
    answerEl.classList.add("empty");
    citationsEl.innerHTML = "<li>No sources yet.</li>";
    citationsEl.classList.add("empty");
    if (artifactsEl) {
      artifactsEl.innerHTML = "<li>No generated files.</li>";
      artifactsEl.classList.add("empty");
    }
    detailsEl.textContent = "{}";
    confidenceEl.textContent = "Confidence --";
  }

  function parseJson(value) {
    try {
      return JSON.parse(value);
    } catch (_) {
      return value;
    }
  }

  function pretty(value) {
    return typeof value === "string" ? value : JSON.stringify(value, null, 2);
  }

  function eventType(payload, fallback) {
    return String(payload && (payload.type || payload.event_type) || fallback || "event");
  }

  function addEvent(name, payload) {
    const record = { name: name || "message", payload };
    eventRecords.push(record);
    eventCountEl.textContent = String(eventRecords.length);
    updateRunMetadata(record);
    updateGraphFromEvent(record);
    renderEvent(record, eventRecords.length);
    renderTimelineNode(record, eventRecords.length);
  }

  function updateRunMetadata(record) {
    const type = eventType(record.payload, record.name);
    const payload = record.payload && record.payload.payload;
    if (type === "workflow_selected" && payload && payload.workflow) {
      workflowEl.textContent = payload.workflow;
    }
    if (type === "agent_spawned") {
      agentCount += 1;
      agentCountEl.textContent = String(agentCount);
    }
    if (type === "tool_call_requested") {
      toolCount += 1;
      toolCountEl.textContent = String(toolCount);
    }
  }

  function renderEvent(record, index) {
    const type = eventType(record.payload, record.name);
    const summary = record.payload && record.payload.summary || type.replaceAll("_", " ");
    const item = document.createElement("li");
    item.className = `activity-item ${classForType(type)}`;
    item.innerHTML = `
      <button type="button">
        <span class="activity-index">${String(index).padStart(2, "0")}</span>
        <span class="activity-copy">
          <strong>${escapeHtml(summary)}</strong>
          <small>${escapeHtml(type)}</small>
        </span>
      </button>`;
    item.querySelector("button").addEventListener("click", () => {
      selectInspector(record.payload, item);
    });
    eventsEl.append(item);
    eventsEl.scrollTop = eventsEl.scrollHeight;
  }

  function renderTimelineNode(record, index) {
    const type = eventType(record.payload, record.name);
    const node = document.createElement("button");
    node.type = "button";
    node.className = `path-node ${classForType(type)}`;
    node.innerHTML = `<span>${String(index).padStart(2, "0")}</span><strong>${escapeHtml(type.replaceAll("_", " "))}</strong>`;
    node.addEventListener("click", () => selectInspector(record.payload, node));
    pathEl.append(node);
  }

  function selectInspector(payload, selectedElement) {
    document.querySelectorAll(".is-selected").forEach((item) => item.classList.remove("is-selected"));
    if (selectedElement) selectedElement.classList.add("is-selected");
    selectedEventEl.textContent = pretty(payload);
  }

  function classForType(type) {
    if (type.includes("failed") || type.includes("error")) return "is-error";
    if (type.includes("cancelled") || type.includes("blocked")) return "is-muted";
    if (type.includes("completed") || type.includes("answer")) return "is-complete";
    if (type.includes("tool")) return "is-tool";
    if (type.includes("agent")) return "is-agent";
    if (type.includes("workflow") || type.includes("plan")) return "is-workflow";
    return "is-neutral";
  }

  function updateGraphFromEvent(record) {
    const payload = record.payload && record.payload.payload;
    const type = eventType(record.payload, record.name);
    if (!payload) return;
    if (type === "graph_node_created" || type === "graph_node_updated") {
      graphNodes.set(payload.node_id, payload);
      renderWorkflowGraph();
    } else if (type === "graph_edge_created") {
      graphEdges.set(payload.edge_id, payload);
      renderWorkflowGraph();
    }
  }

  function renderWorkflowGraph() {
    const nodes = Array.from(graphNodes.values());
    const edges = Array.from(graphEdges.values());
    graphEmptyEl.hidden = nodes.length > 0;
    if (!nodes.length) {
      graphEl.innerHTML = "";
      return;
    }

    const levels = calculateLevels(nodes, edges);
    const order = [...nodes].sort((left, right) => {
      const levelDiff = (levels.get(left.node_id) || 0) - (levels.get(right.node_id) || 0);
      if (levelDiff !== 0) return levelDiff;
      return String(left.node_id).localeCompare(String(right.node_id));
    });
    graphEl.innerHTML = order.map((node) => {
      const status = escapeHtml(node.status || "pending");
      const type = escapeHtml(node.node_type || "node");
      const label = escapeHtml(node.label || node.node_id);
      const depth = Math.min(levels.get(node.node_id) || 0, 4);
      const parentEdge = edges.find((edge) => edge.target === node.node_id);
      const relation = parentEdge ? parentEdge.edge_type : "root";
      return `
        <button class="tree-node" type="button" style="--depth:${depth}" data-node-id="${escapeHtml(node.node_id)}" data-type="${type}" data-status="${status}">
          <span class="node-dot"></span>
          <span class="node-copy">
            <strong>${label}</strong>
            <small>${type} · ${escapeHtml(relation)}</small>
          </span>
          <span class="node-status">${status}</span>
        </button>`;
    }).join("");
    graphEl.querySelectorAll(".tree-node").forEach((element) => {
      element.addEventListener("click", () => {
        selectInspector(graphNodes.get(element.dataset.nodeId) || {}, element);
      });
    });
  }

  function calculateLevels(nodes, edges) {
    const levels = new Map(nodes.map((node) => [node.node_id, 0]));
    for (let pass = 0; pass < nodes.length; pass += 1) {
      let changed = false;
      edges.forEach((edge) => {
        if (!levels.has(edge.source) || !levels.has(edge.target)) return;
        const next = levels.get(edge.source) + 1;
        if (next > levels.get(edge.target)) {
          levels.set(edge.target, next);
          changed = true;
        }
      });
      if (!changed) break;
    }
    return levels;
  }

  function renderCitations(citations) {
    citationsEl.innerHTML = "";
    citationsEl.classList.toggle("empty", !citations.length);
    if (!citations.length) {
      citationsEl.innerHTML = "<li>No sources provided.</li>";
      return;
    }
    citations.forEach((citation, index) => {
      const item = document.createElement("li");
      const title = citation.title || citation.source || `Source ${index + 1}`;
      const url = citation.url || citation.source_url;
      item.innerHTML = url
        ? `<span>${String(index + 1).padStart(2, "0")}</span><a href="${escapeAttribute(url)}" target="_blank" rel="noreferrer">${escapeHtml(title)}</a>`
        : `<span>${String(index + 1).padStart(2, "0")}</span><strong>${escapeHtml(title)}</strong>`;
      citationsEl.append(item);
    });
  }

  function renderResult(result) {
    const answer = result.final_answer || result.answer || result.output || result.result || "";
    answerEl.innerHTML = renderMarkdown(String(answer || ""));
    answerEl.classList.toggle("empty", !answer);
    renderCitations(Array.isArray(result.citations) ? result.citations : []);
    detailsEl.textContent = pretty(result);
    confidenceEl.textContent = typeof result.confidence === "number"
      ? `Confidence ${Math.round(result.confidence * 100)}%`
      : "Confidence --";
  }

  function renderMarkdown(text) {
    if (!text) return "No answer returned.";
    const lines = text.split(/\r?\n/);
    let html = "";
    let unorderedOpen = false;
    let orderedOpen = false;
    let codeOpen = false;
    for (let index = 0; index < lines.length; index += 1) {
      const raw = lines[index];
      const line = raw.trim();
      if (line.startsWith("```")) {
        if (unorderedOpen) { html += "</ul>"; unorderedOpen = false; }
        if (orderedOpen) { html += "</ol>"; orderedOpen = false; }
        html += codeOpen ? "</code></pre>" : "<pre><code>";
        codeOpen = !codeOpen;
        continue;
      }
      if (codeOpen) {
        html += `${escapeHtml(raw)}\n`;
        continue;
      }
      if (
        line.includes("|")
        && index + 1 < lines.length
        && isMarkdownTableSeparator(lines[index + 1])
      ) {
        if (unorderedOpen) { html += "</ul>"; unorderedOpen = false; }
        if (orderedOpen) { html += "</ol>"; orderedOpen = false; }
        const table = renderMarkdownTable(lines, index);
        html += table.html;
        index = table.lastIndex;
        continue;
      }
      if (!line) {
        if (unorderedOpen) { html += "</ul>"; unorderedOpen = false; }
        if (orderedOpen) { html += "</ol>"; orderedOpen = false; }
        continue;
      }
      if (line.startsWith("### ")) html += `<h4>${inlineMarkdown(line.slice(4))}</h4>`;
      else if (line.startsWith("## ")) html += `<h3>${inlineMarkdown(line.slice(3))}</h3>`;
      else if (line.startsWith("# ")) html += `<h2>${inlineMarkdown(line.slice(2))}</h2>`;
      else if (line.startsWith("> ")) html += `<blockquote>${inlineMarkdown(line.slice(2))}</blockquote>`;
      else if (/^[-*]\s+/.test(line)) {
        if (orderedOpen) { html += "</ol>"; orderedOpen = false; }
        if (!unorderedOpen) {
          html += "<ul>";
          unorderedOpen = true;
        }
        html += `<li>${inlineMarkdown(line.replace(/^[-*]\s+/, ""))}</li>`;
      } else if (/^\d+\.\s+/.test(line)) {
        if (unorderedOpen) { html += "</ul>"; unorderedOpen = false; }
        if (!orderedOpen) {
          html += "<ol>";
          orderedOpen = true;
        }
        html += `<li>${inlineMarkdown(line.replace(/^\d+\.\s+/, ""))}</li>`;
      } else {
        if (unorderedOpen) { html += "</ul>"; unorderedOpen = false; }
        if (orderedOpen) { html += "</ol>"; orderedOpen = false; }
        html += `<p>${inlineMarkdown(line)}</p>`;
      }
    }
    if (unorderedOpen) html += "</ul>";
    if (orderedOpen) html += "</ol>";
    if (codeOpen) html += "</code></pre>";
    return html;
  }

  function renderMarkdownTable(lines, startIndex) {
    const headers = splitTableRow(lines[startIndex]);
    const rows = [];
    let index = startIndex + 2;
    while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
      rows.push(splitTableRow(lines[index]));
      index += 1;
    }
    const head = headers.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("");
    const body = rows.map((row) => {
      const cells = headers.map((_, cellIndex) => (
        `<td>${inlineMarkdown(row[cellIndex] || "")}</td>`
      )).join("");
      return `<tr>${cells}</tr>`;
    }).join("");
    return {
      html: `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`,
      lastIndex: index - 1,
    };
  }

  function isMarkdownTableSeparator(line) {
    return splitTableRow(line).every((cell) => /^:?-{3,}:?$/.test(cell));
  }

  function splitTableRow(line) {
    return line.trim().replace(/^\|/, "").replace(/\|$/, "")
      .split("|").map((cell) => cell.trim());
  }

  function inlineMarkdown(text) {
    return escapeHtml(text)
      .replace(/`(.+?)`/g, "<code>$1</code>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  }

  async function fetchResult(taskId) {
    if (resultFetched) return;
    resultFetched = true;
    const response = await fetch(`/tasks/${encodeURIComponent(taskId)}/result`);
    if (!response.ok) throw new Error(`Result request failed: ${response.status}`);
    renderResult(await response.json());
    await fetchArtifacts(taskId);
  }

  async function fetchArtifacts(taskId) {
    if (!artifactsEl) return;
    const response = await fetch(`/tasks/${encodeURIComponent(taskId)}/artifacts`);
    if (!response.ok) return;
    const artifacts = await response.json();
    artifactsEl.innerHTML = "";
    artifactsEl.classList.toggle("empty", artifacts.length === 0);
    if (!artifacts.length) {
      artifactsEl.innerHTML = "<li>No generated files.</li>";
      return;
    }
    artifacts.forEach((artifact, index) => {
      const item = document.createElement("li");
      const url = `/tasks/${encodeURIComponent(taskId)}/artifacts/${encodeURIComponent(artifact.artifact_id)}`;
      item.innerHTML = `<span>${String(index + 1).padStart(2, "0")}</span><a href="${url}">${escapeHtml(artifact.filename)}</a>`;
      artifactsEl.append(item);
    });
  }

  function handleStreamEvent(event, eventName) {
    const payload = parseJson(event.data);
    addEvent(eventName || event.type, payload);
    const namedStatus = terminalStatuses.has(eventName) ? eventName : "";
    const status = payload && (payload.status || payload.task_status || payload.state) || namedStatus;
    if (status) setStatus(status);
    if (activeTaskId && status && terminalStatuses.has(String(status).toLowerCase())) {
      if (source) source.close();
      cancelButton.disabled = true;
      loadHistory();
      if (!["cancelled", "failed"].includes(String(status).toLowerCase())) {
        fetchResult(activeTaskId).catch((error) => addEvent("result_error", error.message));
      }
    }
  }

  function connectStream(taskId) {
    source = new EventSource(`/tasks/${encodeURIComponent(taskId)}/stream`);
    source.onopen = () => setStatus("Running");
    source.onmessage = (event) => handleStreamEvent(event, "message");
    source.onerror = () => {
      if (!resultFetched) setStatus("Stream error");
    };
    ["event", "completed", "degraded", "failed", "cancelled"].forEach((name) => {
      source.addEventListener(name, (event) => handleStreamEvent(event, name));
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    resetView(question);
    submitButton.disabled = true;
    try {
      const endpoint = activeSessionId
        ? `/sessions/${encodeURIComponent(activeSessionId)}/tasks`
        : "/tasks";
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: question }),
      });
      if (!response.ok) throw new Error(`Task request failed: ${response.status}`);
      const payload = await response.json();
      activeTaskId = payload.task_id || payload.id || payload.taskId;
      if (!activeTaskId) throw new Error("Task response did not include a task_id.");
      taskIdEl.textContent = activeTaskId;
      setStatus(payload.status || "Queued");
      cancelButton.disabled = false;
      addEvent("task_created", payload);
      connectStream(activeTaskId);
      if (activeSessionId) loadSessionTasks(activeSessionId);
    } catch (error) {
      setStatus("Error");
      addEvent("error", error.message);
    } finally {
      submitButton.disabled = false;
    }
  });

  cancelButton.addEventListener("click", async () => {
    if (!activeTaskId) return;
    cancelButton.disabled = true;
    try {
      const response = await fetch(`/tasks/${encodeURIComponent(activeTaskId)}/cancel`, { method: "POST" });
      if (!response.ok) throw new Error(`Cancel request failed: ${response.status}`);
      const payload = await response.json();
      setStatus(payload.status || "cancelled");
      addEvent("task_cancelled", payload);
    } catch (error) {
      addEvent("cancel_error", error.message);
    }
  });

  document.querySelectorAll(".prompt-button").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.dataset.prompt || "";
      input.focus();
    });
  });

  async function loadHistory() {
    const historyEl = $("taskHistory");
    historyEl.innerHTML = '<div class="empty-state">Loading history...</div>';
    try {
      const response = await fetch("/tasks?limit=50");
      if (!response.ok) throw new Error(`History request failed: ${response.status}`);
      const tasks = await response.json();
      if (!tasks.length) {
        historyEl.innerHTML = '<div class="empty-state">No saved tasks.</div>';
        return;
      }
      historyEl.innerHTML = tasks.map((task) => `
        <button class="history-item" type="button" data-task-id="${escapeHtml(task.task_id)}">
          <span class="history-copy">
            <strong>${escapeHtml(task.input)}</strong>
            <small>${escapeHtml(task.workflow || "pending")} · ${formatDate(task.created_at)}</small>
          </span>
          <span class="history-status">${escapeHtml(task.status)}</span>
        </button>`).join("");
      historyEl.querySelectorAll(".history-item").forEach((button) => {
        button.addEventListener("click", () => replayTask(button.dataset.taskId));
      });
    } catch (error) {
      historyEl.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    }
  }

  async function loadSessions() {
    const select = $("sessionSelect");
    const previous = activeSessionId;
    const response = await fetch("/sessions?limit=50");
    if (!response.ok) return;
    const sessions = await response.json();
    select.innerHTML = '<option value="">Standalone task</option>' + sessions.map(
      (session) => `<option value="${escapeHtml(session.session_id)}">${escapeHtml(session.title)} (${session.task_count})</option>`
    ).join("");
    if (previous && sessions.some((item) => item.session_id === previous)) {
      select.value = previous;
    }
  }

  async function createSession() {
    const title = window.prompt("Session title", "New long task");
    if (title === null) return;
    const response = await fetch("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title.trim() || "New long task" }),
    });
    if (!response.ok) return;
    const session = await response.json();
    activeSessionId = session.session_id;
    await loadSessions();
    $("sessionSelect").value = activeSessionId;
    await loadSessionTasks(activeSessionId);
  }

  async function loadSessionTasks(sessionId) {
    const container = $("sessionTasks");
    if (!sessionId) {
      container.innerHTML = '<div class="empty-state">Select a session.</div>';
      return;
    }
    const response = await fetch(`/sessions/${encodeURIComponent(sessionId)}`);
    if (!response.ok) {
      container.innerHTML = '<div class="empty-state">Session unavailable.</div>';
      return;
    }
    const payload = await response.json();
    if (!payload.tasks.length) {
      container.innerHTML = '<div class="empty-state">No tasks in this session.</div>';
      return;
    }
    container.innerHTML = payload.tasks.map((task) => `
      <button class="history-item" type="button" data-task-id="${escapeHtml(task.task_id)}">
        <span class="history-copy">
          <strong>${escapeHtml(task.input)}</strong>
          <small>${escapeHtml(task.workflow || "pending")} · ${formatDate(task.created_at)}</small>
        </span>
        <span class="history-status">${escapeHtml(task.status)}</span>
      </button>`).join("");
    container.querySelectorAll(".history-item").forEach((button) => {
      button.addEventListener("click", () => replayTask(button.dataset.taskId));
    });
  }

  async function replayTask(taskId) {
    if (source) source.close();
    source = null;
    activeTaskId = taskId;
    const response = await fetch(`/tasks/${encodeURIComponent(taskId)}/replay`);
    if (!response.ok) {
      selectInspector(`Replay request failed: ${response.status}`);
      return;
    }
    const replay = await response.json();
    resetView(replay.task.input);
    activeTaskId = taskId;
    taskIdEl.textContent = taskId;
    activeSessionId = replay.task.session_id || "";
    $("sessionSelect").value = activeSessionId;
    loadSessionTasks(activeSessionId);
    setStatus(replay.task.status);
    workflowEl.textContent = replay.task.workflow || "Pending";
    cancelButton.disabled = true;
    replay.events.forEach((event) => addEvent("replay", event));
    if (replay.result) renderResult(replay.result);
    fetchArtifacts(taskId).catch(() => {});
    detailsEl.textContent = pretty(replay);
  }

  function formatDate(value) {
    if (!value) return "";
    try {
      return new Date(value).toLocaleString();
    } catch (_) {
      return value;
    }
  }

  $("refreshHistory").addEventListener("click", loadHistory);
  $("newSessionButton").addEventListener("click", createSession);
  $("sessionSelect").addEventListener("change", async (event) => {
    activeSessionId = event.target.value;
    await loadSessionTasks(activeSessionId);
  });
  loadHistory();
  loadSessions();

  function shortLabel(value, limit) {
    const text = String(value || "");
    return escapeHtml(text.length > limit ? `${text.slice(0, limit)}...` : text);
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replaceAll("'", "&#39;");
  }
})();
