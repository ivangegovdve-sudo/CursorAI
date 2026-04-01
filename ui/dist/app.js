"use strict";
const repoSelect = document.querySelector("#repoSelect");
const intervalInput = document.querySelector("#intervalInput");
const statusBox = document.querySelector("#statusBox");
const activeRunBadge = document.querySelector("#activeRunBadge");
const roadmapRepoLabel = document.querySelector("#roadmapRepoLabel");
const roadmapList = document.querySelector("#roadmapList");
const runsList = document.querySelector("#runsList");
const refreshButton = document.querySelector("#refreshButton");
const runNextButton = document.querySelector("#runNextButton");
const startSchedulerButton = document.querySelector("#startSchedulerButton");
const stopSchedulerButton = document.querySelector("#stopSchedulerButton");
async function fetchJson(url, init) {
    const response = await fetch(url, init);
    if (!response.ok) {
        const payload = await response.text();
        throw new Error(payload || `Request failed: ${response.status}`);
    }
    return (await response.json());
}
function renderStatus(status) {
    if (!statusBox || !activeRunBadge)
        return;
    activeRunBadge.textContent = status.active_run ? "Running" : "Idle";
    statusBox.textContent = JSON.stringify({
        scheduler: status.scheduler,
        active_run: status.active_run,
    }, null, 2);
}
function renderRoadmap(tasks, repoLabel) {
    if (!roadmapList || !roadmapRepoLabel)
        return;
    roadmapRepoLabel.textContent = repoLabel;
    roadmapList.innerHTML = "";
    for (const task of tasks) {
        const card = document.createElement("article");
        card.className = "task-card";
        card.innerHTML = `
      <div class="task-status">${task.status}</div>
      <h3>${task.title}</h3>
      <div class="task-meta"><strong>${task.id}</strong> · action: ${task.action}</div>
      <div class="task-meta">Depends on: ${task.depends_on.length ? task.depends_on.join(", ") : "none"}</div>
    `;
        roadmapList.append(card);
    }
}
function renderRuns(runs) {
    if (!runsList)
        return;
    runsList.innerHTML = "";
    for (const run of runs) {
        const card = document.createElement("article");
        card.className = "run-card";
        const finishedAt = String(run.finished_at ?? "");
        const status = String(run.status ?? "unknown");
        const repo = String(run.repo ?? "n/a");
        card.innerHTML = `
      <div class="task-status">${status}</div>
      <h3>${repo}</h3>
      <div class="run-meta">${finishedAt}</div>
      <pre class="code-box">${JSON.stringify(run, null, 2)}</pre>
    `;
        runsList.append(card);
    }
}
async function loadRoadmap(repo) {
    const payload = await fetchJson(`/api/adk/roadmap?repo=${encodeURIComponent(repo)}`);
    renderRoadmap(payload.roadmap.tasks, payload.repo);
}
async function loadDashboard() {
    const selectedRepo = repoSelect?.value ?? "cursorai";
    const [status, runs] = await Promise.all([
        fetchJson("/api/adk/status"),
        fetchJson("/api/adk/runs"),
    ]);
    renderStatus(status);
    renderRuns(runs.runs);
    await loadRoadmap(selectedRepo === "all" ? "cursorai" : selectedRepo);
}
async function runNext() {
    const repo = repoSelect?.value ?? "cursorai";
    await fetchJson("/api/adk/run-next", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo }),
    });
    await loadDashboard();
}
async function startScheduler() {
    const interval = Number(intervalInput?.value ?? "300");
    await fetchJson("/api/adk/scheduler/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ interval_seconds: interval }),
    });
    await loadDashboard();
}
async function stopScheduler() {
    await fetchJson("/api/adk/scheduler/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
    });
    await loadDashboard();
}
refreshButton?.addEventListener("click", () => {
    loadDashboard().catch(console.error);
});
runNextButton?.addEventListener("click", () => {
    runNext().catch(console.error);
});
startSchedulerButton?.addEventListener("click", () => {
    startScheduler().catch(console.error);
});
stopSchedulerButton?.addEventListener("click", () => {
    stopScheduler().catch(console.error);
});
repoSelect?.addEventListener("change", () => {
    loadDashboard().catch(console.error);
});
loadDashboard().catch((error) => {
    if (statusBox) {
        statusBox.textContent = String(error);
    }
});
