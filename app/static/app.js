(function () {
  "use strict";

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const statusNode = document.querySelector("#sync-status, #ai-action-status");
  let insightGenerationRequested = false;

  function setStatus(message, kind) {
    if (!statusNode) return;
    statusNode.textContent = message || "";
    statusNode.className = "action-status" + (kind ? ` ${kind}` : "");
  }

  function setBusy(button, busy, busyText) {
    if (!button) return;
    if (busy) {
      button.dataset.originalText = button.textContent;
      button.disabled = true;
      button.textContent = busyText;
    } else {
      button.disabled = false;
      if (button.dataset.originalText) button.textContent = button.dataset.originalText;
    }
  }

  async function postJson(url, body = null) {
    const requestOptions = {
      method: "POST",
      headers: { "X-CSRF-Token": csrf, Accept: "application/json" },
      credentials: "same-origin",
    };
    if (body && typeof body === "object" && Object.keys(body).length) {
      requestOptions.headers["Content-Type"] = "application/json";
      requestOptions.body = JSON.stringify(body);
    }
    const response = await fetch(url, requestOptions);
    const data = await response.json().catch(() => ({ ok: false, error: "Resposta inválida do servidor." }));
    if (!response.ok || !data.ok) throw new Error(data.error || "A operação falhou.");
    return data;
  }

  async function runSync(button) {
    setBusy(button, true, "Atualizando…");
    setStatus("Buscando perfil e todos os vídeos disponíveis…", "loading");
    try {
      const data = await postJson("/api/sync");
      setStatus(data.summary.message, "success");
      window.setTimeout(() => window.location.reload(), 450);
    } catch (error) {
      setStatus(error.message, "error");
      setBusy(button, false);
    }
  }

  async function runExport(button, kind) {
    setBusy(button, true, "Gerando…");
    setStatus(`Gerando arquivo ${kind.toUpperCase()}…`, "loading");
    try {
      const data = await postJson(`/api/export/${kind}`);
      setStatus(`Arquivo ${data.filename} pronto.`, "success");
      const link = document.createElement("a");
      link.href = data.download_url;
      link.download = data.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  }

  async function runAiAction(button, url, busyText, message, body = null, reload = false) {
    setBusy(button, true, busyText);
    setStatus(message, "loading");
    try {
      const data = await postJson(url, body);
      if (url.includes("generate-insights")) insightGenerationRequested = true;
      setStatus(data.message || "Operação local iniciada.", "success");
      if (reload) window.setTimeout(() => window.location.reload(), 600);
      return data;
    } catch (error) {
      setStatus(error.message, "error");
      return null;
    } finally {
      setBusy(button, false);
    }
  }

  async function fetchAiStatus() {
    const response = await fetch("/api/ai/status", {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("Não foi possível consultar o status da IA.");
    return response.json();
  }

  function renderAiStatus(data) {
    document.querySelectorAll("[data-ai-count]").forEach((node) => {
      const value = data[node.dataset.aiCount];
      if (value !== undefined) node.textContent = value;
    });
    const total = Number(data.total || 0);
    const completed = Number(data.completed || 0);
    const progress = document.querySelector("#ai-progress");
    if (progress) progress.style.width = `${total ? Math.min(100, completed / total * 100) : 0}%`;
    const label = document.querySelector("[data-ai-progress-label]");
    if (label) label.textContent = `${completed} / ${total}`;
    const current = document.querySelector("[data-ai-current]");
    if (current) current.textContent = data.current_video_id ? `${data.current_video_id} · ${data.current_stage || "em andamento"}` : (data.stop_requested ? "Pausa solicitada; termina o vídeo atual" : "Nenhum vídeo em andamento");
    const jobStatus = document.querySelector("[data-ai-job-status]");
    if (jobStatus) {
      jobStatus.textContent = data.job_status || "idle";
      jobStatus.className = `tag ${data.worker_running ? "tag-success" : "tag-warning"}`;
    }
    const error = document.querySelector("[data-ai-last-error]");
    if (error) error.textContent = data.last_error || "";
  }

  async function pollAiStatus() {
    try {
      const data = await fetchAiStatus();
      renderAiStatus(data);
      if (insightGenerationRequested && !data.worker_running && data.job_status === "completed") {
        insightGenerationRequested = false;
        window.setTimeout(() => window.location.reload(), 250);
      }
    } catch (_error) {
      // A transient refresh must not turn into a visible browser exception.
    }
  }

  document.querySelectorAll("[data-action='sync']").forEach((button) => {
    button.addEventListener("click", () => runSync(button));
  });
  document.querySelectorAll("[data-action='export-json']").forEach((button) => {
    button.addEventListener("click", () => runExport(button, "json"));
  });
  document.querySelectorAll("[data-action='export-csv']").forEach((button) => {
    button.addEventListener("click", () => runExport(button, "csv"));
  });

  document.querySelectorAll("[data-action='ai-analyze-library']").forEach((button) => {
    button.addEventListener("click", () => runAiAction(button, "/api/ai/analyze-library", "Iniciando…", "Preparando a fila local…"));
  });
  document.querySelectorAll("[data-action='ai-reanalyze-library']").forEach((button) => {
    button.addEventListener("click", () => {
      if (window.confirm("Reanalisar toda a biblioteca? As métricas históricas serão preservadas.")) {
        runAiAction(button, "/api/ai/analyze-library", "Iniciando…", "Preparando reanálise…", { reanalyze_all: true, confirm: true });
      }
    });
  });
  document.querySelectorAll("[data-action='ai-pause']").forEach((button) => {
    button.addEventListener("click", () => runAiAction(button, "/api/ai/pause", "Solicitando…", "A pausa será aplicada após o vídeo atual…"));
  });
  document.querySelectorAll("[data-action='ai-continue']").forEach((button) => {
    button.addEventListener("click", () => runAiAction(button, "/api/ai/continue", "Continuando…", "Retomando a fila local…"));
  });
  document.querySelectorAll("[data-action='ai-retry-failed']").forEach((button) => {
    button.addEventListener("click", () => runAiAction(button, "/api/ai/retry-failed", "Retentando…", "Colocando falhas novamente na fila…"));
  });
  document.querySelectorAll("[data-action='ai-analyze-video'], [data-action='ai-retry-video'], [data-action='ai-reanalyze-video']").forEach((button) => {
    button.addEventListener("click", () => {
      const force = button.dataset.action === "ai-reanalyze-video" || button.dataset.action === "ai-retry-video";
      const endpoint = `/api/ai/videos/${encodeURIComponent(button.dataset.videoId)}/${force ? "reanalyze" : "analyze"}`;
      runAiAction(button, endpoint, "Enfileirando…", "Enfileirando este vídeo no worker local…", null, true);
    });
  });
  document.querySelectorAll("[data-action='ai-local-file']").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.querySelector("#ai-local-path");
      const localPath = input?.value.trim();
      if (!localPath) {
        setStatus("Informe um caminho absoluto para um MP4.", "error");
        return;
      }
      runAiAction(button, `/api/ai/videos/${encodeURIComponent(button.dataset.videoId)}/local-file`, "Enfileirando…", "Validando o MP4 local…", { local_path: localPath }, true);
    });
  });
  document.querySelectorAll("[data-action='ai-generate-insights']").forEach((button) => {
    button.addEventListener("click", () => runAiAction(button, "/api/ai/generate-insights", "Gerando…", "O Qwen3-VL está preparando os insights locais…", { force: button.dataset.aiForce === "true" }));
  });

  if (document.querySelector("[data-ai-page], [data-ai-insights-page]")) {
    pollAiStatus();
    window.setInterval(pollAiStatus, 2000);
  }

  document.querySelectorAll("[data-dismiss-flash]").forEach((button) => {
    button.addEventListener("click", () => button.closest(".flash")?.remove());
  });

  const sortSelect = document.querySelector("#sort-videos");
  if (sortSelect) {
    sortSelect.addEventListener("change", () => {
      const url = new URL(sortSelect.dataset.sortUrl, window.location.origin);
      url.searchParams.set("sort", sortSelect.value);
      window.location.href = url.toString();
    });
  }

  function initChart() {
    const canvas = document.querySelector("#metrics-chart");
    if (!canvas || typeof Chart === "undefined" || !Array.isArray(window.metricHistory)) return;
    const select = document.querySelector("#metric-select");
    const points = window.metricHistory;
    const labels = points.map((point) => {
      const date = new Date(point.collected_at);
      return Number.isNaN(date.getTime()) ? point.collected_at : date.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    });
    const colors = { views: "#25f4ee", likes: "#fe2c55", comments: "#b28cff", shares: "#f4c95d" };
    const names = { views: "Views", likes: "Likes", comments: "Comentários", shares: "Shares" };
    let chart;
    function draw(metric) {
      const values = points.map((point) => point[metric]);
      if (chart) chart.destroy();
      chart = new Chart(canvas, {
        type: "line",
        data: { labels, datasets: [{ label: names[metric], data: values, borderColor: colors[metric], backgroundColor: `${colors[metric]}22`, fill: true, tension: 0.28, spanGaps: true, pointRadius: 4, pointHoverRadius: 6 }] },
        options: { responsive: true, maintainAspectRatio: false, interaction: { intersect: false, mode: "index" }, plugins: { legend: { labels: { color: "#a3a9b8" } } }, scales: { x: { ticks: { color: "#6f7687" }, grid: { color: "#ffffff10" } }, y: { beginAtZero: true, ticks: { color: "#6f7687" }, grid: { color: "#ffffff10" } } } },
      });
    }
    draw(select?.value || "views");
    select?.addEventListener("change", () => draw(select.value));
  }

  document.addEventListener("DOMContentLoaded", initChart);
})();
