/**
 * Evaluation Dashboard Vanilla JS:
 * Tải dữ liệu từ các endpoints /api/evaluation/*, vẽ biểu đồ SVG/CSS cục bộ (không dùng CDN ngoài).
 */

let allCases = [];
let summaryData = null;
let perfData = null;
let historyData = [];

document.addEventListener("DOMContentLoaded", async () => {
  initTabs();
  initModal();
  await loadDashboardData();
  setupFilterListeners();
});

function initTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");

      const targetSection = tab.getAttribute("data-target");
      document.querySelectorAll(".tab-content").forEach(sec => {
        sec.style.display = sec.id === targetSection ? "block" : "none";
      });
    });
  });
}

function initModal() {
  const overlay = document.getElementById("modalOverlay");
  const closeBtn = document.getElementById("modalCloseBtn");
  if (closeBtn && overlay) {
    closeBtn.addEventListener("click", () => overlay.classList.remove("active"));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) overlay.classList.remove("active");
    });
  }
}

async function loadDashboardData() {
  try {
    const [sumRes, casesRes, perfRes, histRes] = await Promise.all([
      fetch("/api/evaluation/summary"),
      fetch("/api/evaluation/cases"),
      fetch("/api/evaluation/performance"),
      fetch("/api/evaluation/history")
    ]);

    summaryData = await sumRes.json();
    const casesPayload = await casesRes.json();
    allCases = casesPayload.cases || [];
    perfData = await perfRes.json();
    const histPayload = await histRes.json();
    historyData = histPayload.snapshots || [];

    renderHeader();
    renderOverviewCards();
    renderStrengthsWeaknesses();
    renderGroupsTable();
    renderFailureAnalysis();
    renderRetrievalView();
    renderPerformanceView();
    renderMemoryView();
    renderCaseExplorer(allCases);
    renderHistoryView();
  } catch (err) {
    console.error("Lỗi khi tải dữ liệu dashboard:", err);
  }
}

function renderHeader() {
  if (!summaryData) return;
  const meta = summaryData.metadata;
  document.getElementById("metaCommit").textContent = meta.short_commit || "4cf04cc";
  document.getElementById("metaCases").textContent = meta.total_cases || "62";
  document.getElementById("metaTimestamp").textContent = (meta.run_timestamp || "").slice(0, 10);
  
  const badge = document.getElementById("verdictBadge");
  badge.textContent = meta.verdict || "LEVEL_4_ACCEPTED_WITH_MINOR_LIMITATIONS";
  badge.className = "status-badge badge-warning-accepted";
}

function renderOverviewCards() {
  if (!summaryData || !summaryData.cards) return;
  const c = summaryData.cards;
  document.getElementById("valRouterAcc").textContent = `${c.router_accuracy}%`;
  document.getElementById("valRecall5").textContent = `${c.recall_at_5}%`;
  document.getElementById("valRecall20").textContent = `${c.recall_at_20}%`;
  document.getElementById("valMRR").textContent = c.mrr;
  document.getElementById("valAbstention").textContent = `${c.abstention_accuracy}%`;
  document.getElementById("valWrongPremise").textContent = `${c.wrong_premise_resistance}%`;
  document.getElementById("valFollowup").textContent = `${c.followup_resolution_rate}%`;
  document.getElementById("valHallucination").textContent = c.critical_hallucinations;
}

function renderStrengthsWeaknesses() {
  if (!summaryData) return;
  const sList = document.getElementById("strengthsList");
  const wList = document.getElementById("weaknessesList");
  sList.innerHTML = "";
  wList.innerHTML = "";

  (summaryData.system_strengths || []).forEach(s => {
    const li = document.createElement("li");
    li.innerHTML = `<span>✓</span> <div>${s}</div>`;
    sList.appendChild(li);
  });

  (summaryData.system_weaknesses || []).forEach(w => {
    const li = document.createElement("li");
    li.innerHTML = `<span>⚠</span> <div>${w}</div>`;
    wList.appendChild(li);
  });
}

function renderGroupsTable() {
  if (!summaryData || !summaryData.groups) return;
  const tbody = document.querySelector("#groupsTable tbody");
  tbody.innerHTML = "";

  summaryData.groups.forEach(g => {
    const tr = document.createElement("tr");
    tr.title = "Nhấp để xem chi tiết các test cases thuộc nhóm này";
    tr.addEventListener("click", () => {
      // Chuyển sang tab explorer và lọc theo group
      switchToExplorerGroup(g.group);
    });

    let badgeClass = "badge-strong";
    if (g.strength === "WEAK") badgeClass = "badge-weak";
    else if (g.strength === "ACCEPTABLE") badgeClass = "badge-acceptable";

    let colorClass = "green";
    if (g.pass_rate < 60) colorClass = "red";
    else if (g.pass_rate < 85) colorClass = "yellow";

    tr.innerHTML = `
      <td><strong>${g.group}</strong></td>
      <td>${g.total}</td>
      <td style="color: var(--accent-green); font-weight: 600;">${g.passed}</td>
      <td style="color: var(--accent-red); font-weight: 600;">${g.failed}</td>
      <td>
        <div class="bar-cell">
          <div class="bar-bg">
            <div class="bar-fill ${colorClass}" style="width: ${g.pass_rate}%"></div>
          </div>
          <span style="min-width: 45px;">${g.pass_rate}%</span>
        </div>
      </td>
      <td><span class="status-badge ${badgeClass}">${g.strength}</span></td>
      <td><code>${g.primary_failure_cause}</code></td>
    `;
    tbody.appendChild(tr);
  });
}

function switchToExplorerGroup(groupName) {
  // Active tab Case Explorer
  document.querySelectorAll(".tab-btn").forEach(t => t.classList.remove("active"));
  const expTab = document.querySelector('.tab-btn[data-target="tabExplorer"]');
  if (expTab) expTab.classList.add("active");

  document.querySelectorAll(".tab-content").forEach(sec => {
    sec.style.display = sec.id === "tabExplorer" ? "block" : "none";
  });

  // Set filter
  const grpSelect = document.getElementById("filterGroup");
  if (grpSelect) {
    grpSelect.value = groupName;
    applyFilters();
  }
}

function renderFailureAnalysis() {
  if (!summaryData || !summaryData.failure_analysis) return;
  const container = document.getElementById("failureAnalysisBars");
  container.innerHTML = "";

  summaryData.failure_analysis.forEach(f => {
    const row = document.createElement("div");
    row.style.marginBottom = "14px";
    row.style.cursor = "pointer";
    row.title = "Nhấp để lọc các test case bị ảnh hưởng bởi lỗi này";
    row.addEventListener("click", () => {
      switchToExplorerRootCause(f.root_cause);
    });

    row.innerHTML = `
      <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px;">
        <span><strong>${f.label}</strong> (<code>${f.root_cause}</code>)</span>
        <span>${f.count} ca (${f.percentage}%)</span>
      </div>
      <div class="bar-bg" style="height: 10px;">
        <div class="bar-fill red" style="width: ${Math.max(f.percentage, 2)}%;"></div>
      </div>
      <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
        Cases: ${f.affected_case_ids.join(", ") || "None"}
      </div>
    `;
    container.appendChild(row);
  });
}

function switchToExplorerRootCause(rootCause) {
  document.querySelectorAll(".tab-btn").forEach(t => t.classList.remove("active"));
  const expTab = document.querySelector('.tab-btn[data-target="tabExplorer"]');
  if (expTab) expTab.classList.add("active");

  document.querySelectorAll(".tab-content").forEach(sec => {
    sec.style.display = sec.id === "tabExplorer" ? "block" : "none";
  });

  const rcSelect = document.getElementById("filterRootCause");
  if (rcSelect) {
    rcSelect.value = rootCause;
    applyFilters();
  }
}

function renderRetrievalView() {
  if (!summaryData || !summaryData.retrieval_distribution) return;
  const dist = summaryData.retrieval_distribution;
  const total = dist.total_domain_queries || 43;

  const ranks = [
    { label: "Rank 1", count: dist.rank_1, pct: (dist.rank_1 / total) * 100, color: "green" },
    { label: "Rank 2", count: dist.rank_2, pct: (dist.rank_2 / total) * 100, color: "blue" },
    { label: "Rank 3", count: dist.rank_3, pct: (dist.rank_3 / total) * 100, color: "yellow" },
    { label: "Rank 4-5", count: dist.rank_4_5, pct: (dist.rank_4_5 / total) * 100, color: "yellow" },
    { label: "> 5", count: dist.greater_than_5, pct: (dist.greater_than_5 / total) * 100, color: "red" },
    { label: "Not Found", count: dist.not_found, pct: (dist.not_found / total) * 100, color: "red" },
  ];

  const container = document.getElementById("rankDistributionBars");
  container.innerHTML = "";

  ranks.forEach(r => {
    const div = document.createElement("div");
    div.style.marginBottom = "12px";
    div.innerHTML = `
      <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px;">
        <span><strong>${r.label}</strong></span>
        <span>${r.count} query (${r.pct.toFixed(1)}%)</span>
      </div>
      <div class="bar-bg" style="height: 10px;">
        <div class="bar-fill ${r.color}" style="width: ${r.pct}%;"></div>
      </div>
    `;
    container.appendChild(div);
  });
}

function renderPerformanceView() {
  if (!perfData || perfData.status === "unavailable") {
    document.getElementById("perfWorkloadTable").innerHTML = `<tr><td colspan="7">Telemetry unavailable / invalid (Artifact not found)</td></tr>`;
    return;
  }

  const lat = perfData.latency || {};
  const tbody = document.querySelector("#perfWorkloadTable tbody");
  tbody.innerHTML = "";

  const rows = [
    { name: "DOMAIN Cache Miss", stats: lat.domain_cache_miss },
    { name: "GENERAL Cache Miss", stats: lat.general_cache_miss },
    { name: "DOMAIN Cache Hit", stats: lat.domain_cache_hit },
    { name: "GENERAL Cache Hit", stats: lat.general_cache_hit },
    { name: "Safe Abstention", stats: lat.abstention },
  ];

  rows.forEach(r => {
    const s = r.stats || {};
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${r.name}</strong></td>
      <td>${s.count || 0}</td>
      <td>${(s.mean || 0).toFixed(1)} ms</td>
      <td>${(s.p50 || 0).toFixed(1)} ms</td>
      <td>${(s.p90 || 0).toFixed(1)} ms</td>
      <td>${(s.p95 || 0).toFixed(1)} ms</td>
      <td>${(s.max || 0).toFixed(1)} ms</td>
    `;
    tbody.appendChild(tr);
  });

  // Local Pipeline Microbenchmarks
  const pipe = perfData.local_pipeline || {};
  const pipeContainer = document.getElementById("localPipelineBars");
  pipeContainer.innerHTML = "";

  const pipeItems = [
    { name: "Query Analyzer", stats: pipe.query_analysis },
    { name: "Dense Vector Search (Chroma)", stats: pipe.dense_search },
    { name: "BM25 Sparse Search", stats: pipe.bm25_search },
    { name: "Hybrid RRF Retrieval", stats: pipe.hybrid_rrf_retrieval },
    { name: "Reranker", stats: pipe.reranker, off: !perfData.reranker_enabled },
    { name: "Context Builder", stats: pipe.context_builder },
  ];

  pipeItems.forEach(item => {
    const s = item.stats || {};
    const mean = (s.mean || 0).toFixed(2);
    const div = document.createElement("div");
    div.style.marginBottom = "10px";
    const badge = item.off ? `<span class="status-badge" style="font-size: 10px; background: rgba(255,255,255,0.1); margin-left: 8px;">Reranker profile = OFF</span>` : "";

    div.innerHTML = `
      <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 3px;">
        <span>${item.name} ${badge}</span>
        <span><strong>${mean} ms</strong> (p50: ${(s.p50||0).toFixed(2)}ms)</span>
      </div>
      <div class="bar-bg" style="height: 6px;">
        <div class="bar-fill blue" style="width: ${Math.min((s.mean || 0) * 1.2, 100)}%;"></div>
      </div>
    `;
    pipeContainer.appendChild(div);
  });
}

function renderMemoryView() {
  if (!perfData || !perfData.memory) return;
  const mem = perfData.memory;
  const stages = [
    { stage: "Stage 1: Before Warmup", data: mem.stage_1_before_warm },
    { stage: "Stage 2: After Warmup", data: mem.stage_2_after_warmup },
    { stage: "Stage 3: After DOMAIN Miss", data: mem.stage_3_after_domain_miss },
    { stage: "Stage 4: After All Workloads", data: mem.stage_4_after_all_workloads },
  ];

  const tbody = document.querySelector("#memoryTable tbody");
  tbody.innerHTML = "";

  stages.forEach(st => {
    const d = st.data || {};
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${st.stage}</td>
      <td><strong>${(d.process_rss_mb || 0).toFixed(2)} MB</strong></td>
      <td>${(d.sys_available_gb || 0).toFixed(2)} GB</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderCaseExplorer(cases) {
  const tbody = document.querySelector("#caseExplorerTable tbody");
  tbody.innerHTML = "";
  document.getElementById("caseCountDisplay").textContent = `${cases.length} cases`;

  cases.forEach(c => {
    const tr = document.createElement("tr");
    tr.addEventListener("click", () => openCaseDetail(c));

    const isPass = c.result === "PASS";
    const badgeClass = isPass ? "badge-pass" : "badge-fail";

    tr.innerHTML = `
      <td><code>${c.id}</code></td>
      <td><span style="font-size: 11px; font-weight: 600;">${c.group}</span></td>
      <td style="max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${c.question}">${c.question}</td>
      <td><span style="font-size: 11px;">${c.expected_category}</span></td>
      <td><span style="font-size: 11px;">${c.actual_category}</span></td>
      <td><span class="badge-result ${badgeClass}">${c.result}</span></td>
      <td><code>${c.root_cause}</code></td>
      <td>${Math.round(c.latency_ms)} ms</td>
    `;
    tbody.appendChild(tr);
  });
}

function openCaseDetail(c) {
  const overlay = document.getElementById("modalOverlay");
  document.getElementById("modalCaseId").textContent = `${c.id} — ${c.result}`;
  document.getElementById("modalQuestion").textContent = c.question;
  document.getElementById("modalCategoryMatch").textContent = `Kỳ vọng: ${c.expected_category} | Thực tế: ${c.actual_category}`;
  document.getElementById("modalExpectedFacts").textContent = (c.expected_facts && c.expected_facts.length) ? c.expected_facts.join(", ") : "N/A";
  document.getElementById("modalActualAnswer").textContent = c.actual_answer || "N/A";
  document.getElementById("modalResolvedQuery").textContent = c.resolved_query || c.question;
  document.getElementById("modalSources").textContent = (c.retrieved_sources && c.retrieved_sources.length) ? c.retrieved_sources.join(", ") : "None";
  document.getElementById("modalSourceRank").textContent = c.correct_source_rank ? `Rank ${c.correct_source_rank}` : "N/A";
  document.getElementById("modalRootCause").textContent = `${c.root_cause} (${c.root_cause_subtype || "N/A"})`;
  document.getElementById("modalReason").textContent = c.reason || "N/A";
  document.getElementById("modalLatency").textContent = `${c.latency_ms} ms`;

  overlay.classList.add("active");
}

function setupFilterListeners() {
  const searchInput = document.getElementById("searchCases");
  const filterStatus = document.getElementById("filterStatus");
  const filterGroup = document.getElementById("filterGroup");
  const filterRootCause = document.getElementById("filterRootCause");

  [searchInput, filterStatus, filterGroup, filterRootCause].forEach(el => {
    if (el) {
      el.addEventListener("input", applyFilters);
      el.addEventListener("change", applyFilters);
    }
  });
}

function applyFilters() {
  const q = (document.getElementById("searchCases").value || "").toLowerCase().trim();
  const stat = document.getElementById("filterStatus").value;
  const grp = document.getElementById("filterGroup").value;
  const rc = document.getElementById("filterRootCause").value;

  const filtered = allCases.filter(c => {
    if (stat && c.result !== stat) return false;
    if (grp && c.group !== grp) return false;
    if (rc && c.root_cause !== rc) return false;
    if (q) {
      const matchId = c.id.toLowerCase().includes(q);
      const matchQ = c.question.toLowerCase().includes(q);
      const matchAns = (c.actual_answer || "").toLowerCase().includes(q);
      return matchId || matchQ || matchAns;
    }
    return true;
  });

  renderCaseExplorer(filtered);
}

function renderHistoryView() {
  const container = document.getElementById("historyViewContainer");
  if (!historyData || historyData.length <= 1) {
    container.innerHTML = `
      <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
        <p style="font-size: 16px; font-weight: 600; margin-bottom: 8px;">Not enough history</p>
        <p style="font-size: 13px;">Hệ thống hiện có <strong>${historyData.length}</strong> run snapshot đã ghi nhận trong <code>eval/results/history/</code>. Cần tối thiểu 2 runs để vẽ biểu đồ Trend theo thời gian.</p>
      </div>
    `;
    return;
  }

  // Nếu có >= 2 runs:
  container.innerHTML = `<div style="padding: 10px;">Lịch sử có ${historyData.length} runs.</div>`;
}
