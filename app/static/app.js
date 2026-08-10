(function () {
  "use strict";

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const statusNode = document.querySelector("#sync-status");

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

  async function postJson(url) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "X-CSRF-Token": csrf, Accept: "application/json" },
      credentials: "same-origin",
    });
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

  document.querySelectorAll("[data-action='sync']").forEach((button) => {
    button.addEventListener("click", () => runSync(button));
  });
  document.querySelectorAll("[data-action='export-json']").forEach((button) => {
    button.addEventListener("click", () => runExport(button, "json"));
  });
  document.querySelectorAll("[data-action='export-csv']").forEach((button) => {
    button.addEventListener("click", () => runExport(button, "csv"));
  });

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
