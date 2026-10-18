let currentUser = null;

const POSITION_LABELS = {
  agree: "赞成",
  disagree: "反对",
  neutral: "中立",
};

const TOPIC_STATUS_LABELS = {
  open: "讨论中",
  closed: "已结束",
};

const NOTIFICATION_KIND_LABELS = {
  report_created: "待处理举报",
  statement_hidden: "发言被隐藏",
  report_resolved: "举报已处理",
  report_dismissed: "举报已驳回",
};

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function positionBadge(position) {
  const label = POSITION_LABELS[position] || position;
  const safe = POSITION_LABELS[position] ? position : "neutral";
  return `<span class="position-badge position-${safe}">${escapeHtml(
    label
  )}</span>`;
}

function statusBadge(status) {
  const label = TOPIC_STATUS_LABELS[status] || status;
  return `<span class="status-badge status-${status}">${escapeHtml(
    label
  )}</span>`;
}

function categoryBadge(category) {
  if (!category) {
    return '<span class="muted">未分类</span>';
  }
  return `<span class="category-badge">${escapeHtml(category.name)}</span>`;
}

function documentLinkHtml(topic) {
  if (!topic.document) {
    return '<span class="muted">未关联</span>';
  }
  const versionText = topic.version
    ? ` <span class="muted">· v${topic.version.version_number}</span>`
    : "";
  return `<a href="../documents/document-detail.html?id=${
    topic.document.id
  }">${escapeHtml(topic.document.title)}</a>${versionText}`;
}

function documentCell(topic) {
  return topic.document
    ? documentLinkHtml(topic)
    : '<span class="muted">-</span>';
}

function renderConclusion(topic, canManage) {
  const conclusion = topic.conclusion;
  if (conclusion) {
    const sharedText = conclusion.shared ? "已回写到关联文档" : "未回写文档";
    return `
      <div class="conclusion">
        <div class="conclusion-head">
          <h3>最终结论</h3>
          <span class="conclusion-meta">${escapeHtml(
            conclusion.by ? conclusion.by.name : "未知"
          )} · ${formatTime(conclusion.at)} · ${sharedText}</span>
          ${
            canManage
              ? '<button class="btn btn-outline btn-sm" id="editConclusionButton" type="button">修改结论</button>'
              : ""
          }
        </div>
        <p class="conclusion-text">${escapeHtml(conclusion.text)}</p>
      </div>
    `;
  }
  if (!canManage) {
    return "";
  }
  return `
    <div class="conclusion conclusion-empty">
      <span class="muted">还没有最终结论。讨论收敛后，管理员或发起人可以补录结论。</span>
      <button class="btn btn-outline btn-sm" id="editConclusionButton" type="button">补录最终结论</button>
    </div>
  `;
}

function renderConclusionForm(topic) {
  const shareHint = topic.document
    ? `同时回写到关联文档《${escapeHtml(topic.document.title)}》`
    : "同时回写到关联文档（当前没有关联文档）";
  return `
    <div class="conclusion-form" id="conclusionForm" hidden>
      <label for="conclusionText">最终结论/决议</label>
      <textarea id="conclusionText" rows="4" maxlength="2000"
        placeholder="写清最终决定、责任人和时间点"></textarea>
      <label class="conclusion-share">
        <input type="checkbox" id="conclusionShare" ${topic.document ? "" : "disabled"} />
        ${shareHint}
      </label>
      <div class="actions">
        <button class="btn btn-primary btn-sm" id="saveConclusionButton" type="button">保存结论</button>
        <button class="btn btn-outline btn-sm" id="cancelConclusionButton" type="button">取消</button>
      </div>
    </div>
  `;
}

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

async function apiRequest(path, options = {}, { redirectOn401 = true } = {}) {
  const config = {
    credentials: "same-origin",
    ...options,
  };

  if (config.body && !(config.body instanceof FormData)) {
    config.headers = {
      "Content-Type": "application/json",
      ...(config.headers || {}),
    };
  }

  const response = await fetch(path, config);
  let payload = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    payload = await response.json();
  }

  if (response.status === 401) {
    if (redirectOn401 && document.body.dataset.page !== "login") {
      const next = window.location.pathname + window.location.search;
      window.location.href =
        "../documents/index.html?next=" + encodeURIComponent(next);
    }
    const error = new Error(payload?.error?.message || "请先登录");
    error.status = 401;
    throw error;
  }

  if (!response.ok) {
    const error = new Error(
      payload?.error?.message || `请求失败（${response.status}）`
    );
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) {
    return null;
  }
  return payload?.data ?? payload;
}

async function getCurrentUser() {
  if (currentUser) {
    return currentUser;
  }
  currentUser = await apiRequest("/api/auth/me");
  return currentUser;
}

async function logout() {
  try {
    await apiRequest("/api/auth/logout", { method: "POST" });
  } catch (_) {
    // 服务端会话已经失效也没关系，本地状态照常清掉
  }
  currentUser = null;
  window.location.href = "../documents/index.html";
}

function renderTopbar(user) {
  const avatar = user.avatar_url
    ? `<img class="avatar" src="${escapeHtml(user.avatar_url)}" alt="微信头像" />`
    : "";
  const wechatTag = user.wechat_bound
    ? '<span class="tag-wechat">微信</span>'
    : "";
  const adminLinks =
    user.role === "admin" ? '<a href="qa-categories.html">问答分类</a>' : "";
  const reportLink =
    user.role === "admin"
      ? `<a href="reports.html" class="nav-badge-link">举报处理<span class="nav-badge" id="pendingReportBadge" hidden></span></a>`
      : "";
  document.querySelectorAll("#topbar").forEach((node) => {
    node.innerHTML = `
      <nav class="admin-nav">
        <a href="/">工作台</a>
        <a href="../documents/categories.html">文档管理</a>
        <a href="index.html">问答话题</a>
        <a href="notifications.html" class="nav-badge-link">通知<span class="nav-badge" id="unreadBadge" hidden></span></a>
        ${reportLink}
        ${adminLinks}
        <a href="../documents/account.html">账号设置</a>
      </nav>
      <span class="user-pill">${avatar}${escapeHtml(user.name)} · ${
        user.role === "admin" ? "管理员" : "教师"
      }${wechatTag}</span>
      <button class="btn btn-outline" id="logoutButton" type="button">退出</button>
    `;
  });
  document.querySelectorAll("#logoutButton").forEach((button) => {
    button.addEventListener("click", logout);
  });
}

async function requireUser() {
  const user = await getCurrentUser();
  renderTopbar(user);
  // 徽标是锦上添花，拿不到也不影响页面
  refreshTopbarBadges();
  return user;
}

async function refreshTopbarBadges() {
  try {
    const counts = await apiRequest("/api/qa/notifications/unread-count");
    const unreadBadge = document.getElementById("unreadBadge");
    if (unreadBadge) {
      unreadBadge.textContent = counts.unread > 99 ? "99+" : String(counts.unread);
      unreadBadge.hidden = !counts.unread;
    }
    const pendingBadge = document.getElementById("pendingReportBadge");
    if (pendingBadge) {
      pendingBadge.textContent =
        counts.pending_reports > 99 ? "99+" : String(counts.pending_reports);
      pendingBadge.hidden = !counts.pending_reports;
    }
  } catch (_) {
    // 忽略：徽标失败不该影响主流程
  }
}

function showPageMessage(containerId, message, isError = false) {
  const container = document.getElementById(containerId);
  if (!container) {
    alert(message);
    return;
  }
  container.innerHTML = `
    <div class="${isError ? "notice" : "notice notice-ok"}">
      ${escapeHtml(message)}
    </div>
  `;
}

function renderTopicRow(topic) {
  return `
    <tr>
      <td><a href="topic.html?id=${topic.id}">${escapeHtml(topic.title)}</a></td>
      <td>${categoryBadge(topic.category)}</td>
      <td>${documentCell(topic)}</td>
      <td>${escapeHtml(topic.creator.name)}</td>
      <td>${statusBadge(topic.status)}</td>
      <td>${topic.statement_count}</td>
      <td>${topic.speaker_count}</td>
      <td>${formatTime(topic.latest_statement_at || topic.updated_at)}</td>
    </tr>
  `;
}

async function initTopicList() {
  await requireUser();
  const container = document.getElementById("topicList");
  const searchInput = document.getElementById("searchInput");
  const categoryFilter = document.getElementById("categoryFilter");
  const statusFilter = document.getElementById("statusFilter");
  const sortFilter = document.getElementById("sortFilter");
  const resetButton = document.getElementById("resetFilters");
  const hintContainer = document.getElementById("topicFilterHint");
  const pagerContainer = document.getElementById("topicPager");
  // 从文档详情页跳转过来时，只显示该文档相关的话题
  const documentIdFilter = qs("document_id");
  const pageSize = 20;
  let page = 1;

  async function loadCategories() {
    const categories = await apiRequest("/api/qa/categories");
    categoryFilter.innerHTML =
      '<option value="">全部分类</option>' +
      '<option value="none">未分类</option>' +
      categories
        .map(
          (category) =>
            `<option value="${category.id}">${escapeHtml(category.name)}</option>`
        )
        .join("");
  }

  function buildQuery() {
    const params = new URLSearchParams();
    const q = searchInput.value.trim();
    const category = categoryFilter.value;
    const status = statusFilter.value;
    const sort = sortFilter.value;
    if (q) {
      params.set("q", q);
    }
    if (category) {
      params.set("category_id", category);
    }
    if (documentIdFilter) {
      params.set("document_id", documentIdFilter);
    }
    if (status) {
      params.set("status", status);
    }
    if (sort && sort !== "latest") {
      params.set("sort", sort);
    }
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    const query = params.toString();
    return query ? `?${query}` : "";
  }

  function renderPager(result) {
    if (!pagerContainer) {
      return;
    }
    const totalPages = result.total_pages || 0;
    pagerContainer.innerHTML = `
      <span class="muted">共 ${result.total} 个话题${
        totalPages > 1 ? ` · 第 ${result.page} / ${totalPages} 页` : ""
      }</span>
      <span class="pager-actions">
        <button class="btn btn-outline btn-sm" id="prevPageButton" type="button" ${
          result.page <= 1 ? "disabled" : ""
        }>上一页</button>
        <button class="btn btn-outline btn-sm" id="nextPageButton" type="button" ${
          result.page >= totalPages ? "disabled" : ""
        }>下一页</button>
      </span>
    `;

    const prevButton = document.getElementById("prevPageButton");
    const nextButton = document.getElementById("nextPageButton");
    if (prevButton) {
      prevButton.addEventListener("click", () => {
        if (page > 1) {
          page -= 1;
          load();
        }
      });
    }
    if (nextButton) {
      nextButton.addEventListener("click", () => {
        if (page < totalPages) {
          page += 1;
          load();
        }
      });
    }
  }

  async function load() {
    container.innerHTML =
      '<tr><td colspan="8" class="muted">加载中…</td></tr>';
    try {
      const result = await apiRequest(`/api/qa/topics${buildQuery()}`);
      const topics = result.items || [];
      page = result.page || page;
      container.innerHTML = topics.length
        ? topics.map(renderTopicRow).join("")
        : '<tr><td colspan="8" class="muted">没有符合条件的话题。</td></tr>';
      // 页码越界（比如筛选后页数变少）时退回最后一页
      if (!topics.length && result.total > 0) {
        const lastPage = Math.max(1, result.total_pages || 1);
        if (page !== lastPage) {
          page = lastPage;
          return load();
        }
      }
      renderPager(result);
    } catch (error) {
      container.innerHTML = `<tr><td colspan="8" class="notice">${escapeHtml(
        error.message
      )}</td></tr>`;
      if (pagerContainer) {
        pagerContainer.innerHTML = "";
      }
    }
  }

  function reloadFirstPage() {
    page = 1;
    load();
  }

  async function renderDocumentHint() {
    if (!hintContainer || !documentIdFilter) {
      return;
    }
    try {
      const doc = await apiRequest(`/api/documents/${documentIdFilter}`);
      hintContainer.innerHTML = `
        <div class="notice notice-ok topic-filter-hint">
          正在查看与文档《${escapeHtml(doc.title)}》相关的话题。
          <a href="index.html">查看全部话题</a>
        </div>
      `;
    } catch (_) {
      // 文档信息拿不到时不影响列表展示
    }
  }

  searchInput.addEventListener("input", debounce(reloadFirstPage, 300));
  categoryFilter.addEventListener("change", reloadFirstPage);
  statusFilter.addEventListener("change", reloadFirstPage);
  sortFilter.addEventListener("change", reloadFirstPage);
  resetButton.addEventListener("click", () => {
    searchInput.value = "";
    categoryFilter.value = "";
    statusFilter.value = "";
    sortFilter.value = "latest";
    reloadFirstPage();
  });

  try {
    await loadCategories();
  } catch (_) {
    // 分类加载失败时不阻塞话题列表展示
  }
  await renderDocumentHint();
  await load();
}

function summaryVerdict(summary) {
  return summary.consensus_reached
    ? '<span class="summary-verdict is-ok">已形成初步统一意见</span>'
    : '<span class="summary-verdict is-pending">意见尚未统一</span>';
}

function renderSummary(summary) {
  const total = summary.statement_count || 0;
  const agree = summary.positions?.agree || 0;
  const disagree = summary.positions?.disagree || 0;
  const neutral = summary.positions?.neutral || 0;

  function bar(count) {
    const percent = total ? Math.round((count / total) * 100) : 0;
    return `
      <div class="summary-bar-row">
        <span class="summary-bar-label">赞成</span>
        <span class="summary-bar-track">
          <span class="summary-bar-fill position-agree" style="width:${percent}%"></span>
        </span>
        <span class="summary-bar-count">${count}</span>
      </div>
    `;
  }

  return `
    <p class="summary-text">${escapeHtml(summary.summary_text || "")}</p>
    <div class="summary-stats">
      <span>发言 ${total} 条</span>
      <span>参与 ${summary.speaker_count || 0} 人</span>
    </div>
    ${bar(agree)}
    <div class="summary-bar-row">
      <span class="summary-bar-label">反对</span>
      <span class="summary-bar-track">
        <span class="summary-bar-fill position-disagree" style="width:${
          total ? Math.round((disagree / total) * 100) : 0
        }%"></span>
      </span>
      <span class="summary-bar-count">${disagree}</span>
    </div>
    <div class="summary-bar-row">
      <span class="summary-bar-label">中立</span>
      <span class="summary-bar-track">
        <span class="summary-bar-fill position-neutral" style="width:${
          total ? Math.round((neutral / total) * 100) : 0
        }%"></span>
      </span>
      <span class="summary-bar-count">${neutral}</span>
    </div>
  `;
}

async function initTopicDetail() {
  const user = await requireUser();
  const topicId = qs("id");
  const container = document.getElementById("detail");
  const statementForm = document.getElementById("statementForm");

  let topic = null;
  // AI 摘要已落库：每次 reload 从话题数据里取，stale 表示生成后又有新发言
  let aiSummaryText = null;
  let aiSummaryStale = false;
  // 轮询用：只有数据真的变了才重渲染，避免打断阅读和输入
  let lastSignature = null;
  let pollTimer = null;
  const pollIntervalMs = 10000;
  let reportTargetId = null;

  function topicSignature(data) {
    return [
      data.status,
      data.updated_at,
      data.statement_count,
      data.speaker_count,
      data.category ? data.category.id : "",
      data.document ? data.document.id : "",
      data.version ? data.version.id : "",
      data.conclusion ? data.conclusion.at : "",
      data.ai_summary ? data.ai_summary.generated_at : "",
      data.ai_summary && data.ai_summary.stale ? "stale" : "",
    ].join("|");
  }

  function markLiveHint() {
    const node = document.getElementById("liveHint");
    if (node) {
      node.textContent =
        "实时更新 · 上次刷新 " +
        new Date().toLocaleTimeString("zh-CN", { hour12: false });
    }
  }

  function hasOpenConclusionForm() {
    // 结论表单或举报表单开着时暂停轮询，避免打断正在输入的内容
    const conclusionForm = document.getElementById("conclusionForm");
    const reportForm = document.getElementById("reportForm");
    return Boolean(
      (conclusionForm && !conclusionForm.hidden) ||
        (reportForm && !reportForm.hidden)
    );
  }

  function hideReportForm() {
    reportTargetId = null;
    const form = document.getElementById("reportForm");
    const reason = document.getElementById("reportReason");
    if (form) {
      form.hidden = true;
    }
    if (reason) {
      reason.value = "";
    }
  }

  async function pollOnce() {
    if (document.visibilityState !== "visible" || hasOpenConclusionForm()) {
      return;
    }
    try {
      const data = await apiRequest(
        `/api/qa/topics/${topicId}`,
        {},
        { redirectOn401: false }
      );
      if (topicSignature(data) === lastSignature) {
        markLiveHint();
        return;
      }
      await reload(data);
    } catch (_) {
      // 轮询失败静默跳过，等下一次
    }
  }

  function startPolling() {
    if (pollTimer) {
      return;
    }
    pollTimer = setInterval(pollOnce, pollIntervalMs);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        pollOnce();
      }
    });
  }

  async function reload(prefetched) {
    try {
      topic = prefetched || (await apiRequest(`/api/qa/topics/${topicId}`));
      lastSignature = topicSignature(topic);
      document.getElementById("pageTitle").textContent = topic.title;
      aiSummaryText = topic.ai_summary ? topic.ai_summary.text : null;
      aiSummaryStale = topic.ai_summary ? Boolean(topic.ai_summary.stale) : false;

      const canClose =
        topic.status === "open" &&
        (user.role === "admin" || user.id === topic.creator.id);
      const canManage =
        user.role === "admin" || user.id === topic.creator.id;

      container.innerHTML = `
        <div class="card">
          <dl class="detail-list">
            <dt>发起人</dt><dd>${escapeHtml(topic.creator.name)}</dd>
            <dt>分类</dt>
            <dd>
              <span id="topicCategory">${categoryBadge(topic.category)}</span>
              ${
                canManage
                  ? `
                    <select id="categorySelect" class="inline-select" hidden></select>
                    <button class="btn btn-outline btn-sm" id="saveCategoryButton" type="button" hidden>保存</button>
                    <button class="btn btn-outline btn-sm" id="editCategoryButton" type="button">修改分类</button>
                  `
                  : ""
              }
            </dd>
            <dt>关联文档</dt>
            <dd>
              <span id="topicDocument">${documentLinkHtml(topic)}</span>
              ${
                canManage
                  ? `
                    <span id="documentEditor" hidden>
                      <select id="documentSelect" class="inline-select"></select>
                      <select id="versionSelect" class="inline-select" hidden></select>
                      <button class="btn btn-outline btn-sm" id="saveDocumentButton" type="button">保存</button>
                      <button class="btn btn-outline btn-sm" id="cancelDocumentButton" type="button">取消</button>
                    </span>
                    <button class="btn btn-outline btn-sm" id="editDocumentButton" type="button">修改关联</button>
                  `
                  : ""
              }
            </dd>
            <dt>状态</dt><dd>${statusBadge(topic.status)}</dd>
            <dt>结束时间</dt><dd>${
              topic.ends_at ? formatTime(topic.ends_at) : "未设置"
            }</dd>
            <dt>创建时间</dt><dd>${formatTime(topic.created_at)}</dd>
            <dt>说明</dt><dd>${escapeHtml(topic.description || "-")}</dd>
          </dl>
          ${renderConclusion(topic, canManage)}
          ${canManage ? renderConclusionForm(topic) : ""}
          <div class="actions">
            ${
              canClose
                ? '<button class="btn btn-outline" id="closeTopicButton" type="button">结束话题</button>'
                : ""
            }
            <a class="btn btn-outline" href="/api/qa/topics/${topic.id}/export">导出讨论</a>
            <a class="btn btn-outline" href="index.html">返回话题列表</a>
          </div>
        </div>

        <section class="card summary-card">
          <div class="summary-head">
            <h2>意见汇总</h2>
            ${summaryVerdict(topic.summary || {})}
          </div>
          ${renderSummary(topic.summary || {})}
          <div class="ai-summary">
            <div class="ai-summary-head">
              <button class="btn btn-outline btn-sm" id="aiSummaryButton" type="button">AI 生成决策摘要</button>
              <span class="muted">由模型依据下方发言生成，仅供参考；是否统一的判定仍以规则汇总为准</span>
            </div>
            <p class="ai-summary-note" id="aiSummaryNote" hidden></p>
            <div id="aiSummaryPanel" class="ai-summary-panel" hidden></div>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <h2>讨论时间线</h2>
            <span class="card-head-meta">
              ${
                user.role === "admin" && topic.hidden_statement_count
                  ? `<span class="hidden-badge">已隐藏 ${topic.hidden_statement_count} 条</span>`
                  : ""
              }
              <span class="muted live-hint" id="liveHint"></span>
            </span>
          </div>
          <div id="reportForm" class="report-form" hidden>
            <div class="report-form-head">
              <strong id="reportTarget">举报发言</strong>
              <button class="btn btn-outline btn-sm" id="cancelReportButton" type="button">取消</button>
            </div>
            <textarea id="reportReason" rows="3" maxlength="500"
              placeholder="请说明举报理由，例如人身攻击、与主题无关的广告等"></textarea>
            <div class="actions">
              <button class="btn btn-primary btn-sm" id="submitReportButton" type="button">提交举报</button>
            </div>
          </div>
          <div id="timeline" class="timeline"></div>
        </section>
      `;

      renderTimeline(topic.statements || []);

      const submitReportButton = document.getElementById("submitReportButton");
      if (submitReportButton) {
        submitReportButton.addEventListener("click", async () => {
          const reasonNode = document.getElementById("reportReason");
          const reason = reasonNode ? reasonNode.value.trim() : "";
          if (!reason) {
            alert("请填写举报理由");
            return;
          }
          if (!reportTargetId) {
            hideReportForm();
            return;
          }
          submitReportButton.disabled = true;
          try {
            await apiRequest(
              `/api/qa/topics/${topicId}/statements/${reportTargetId}/reports`,
              { method: "POST", body: JSON.stringify({ reason }) }
            );
            hideReportForm();
            alert("举报已提交，管理员会尽快处理。");
          } catch (error) {
            alert(error.message);
          } finally {
            submitReportButton.disabled = false;
          }
        });
      }

      const cancelReportButton = document.getElementById("cancelReportButton");
      if (cancelReportButton) {
        cancelReportButton.addEventListener("click", hideReportForm);
      }

      const aiSummaryButton = document.getElementById("aiSummaryButton");
      const aiSummaryPanel = document.getElementById("aiSummaryPanel");
      const aiSummaryNote = document.getElementById("aiSummaryNote");

      function showAiNote(message) {
        if (!aiSummaryNote) {
          return;
        }
        aiSummaryNote.textContent = message || "";
        aiSummaryNote.hidden = !message;
      }

      if (aiSummaryButton) {
        if (aiSummaryText) {
          aiSummaryButton.textContent = "重新生成 AI 摘要";
          if (aiSummaryPanel) {
            aiSummaryPanel.hidden = false;
            aiSummaryPanel.textContent = aiSummaryText;
          }
          if (aiSummaryStale) {
            showAiNote("摘要生成后又有新发言，建议重新生成。");
          }
        }
        aiSummaryButton.addEventListener("click", async () => {
          aiSummaryButton.disabled = true;
          aiSummaryButton.textContent = "生成中…";
          showAiNote("");
          const hadSummary = Boolean(aiSummaryText);
          if (aiSummaryPanel) {
            aiSummaryPanel.hidden = false;
            aiSummaryPanel.textContent = "正在生成本话题的决策摘要，请稍候…";
          }
          try {
            const result = await apiRequest(
              `/api/qa/topics/${topicId}/ai-summary`,
              { method: "POST" }
            );
            aiSummaryText = result.summary_text || "";
            aiSummaryStale = false;
            if (aiSummaryPanel) {
              aiSummaryPanel.textContent = aiSummaryText;
            }
            aiSummaryButton.textContent = "重新生成 AI 摘要";
          } catch (error) {
            if (hadSummary && aiSummaryPanel) {
              // 保留上一次的摘要，只提示这次生成失败的原因
              aiSummaryPanel.textContent = aiSummaryText;
            } else {
              aiSummaryText = null;
              if (aiSummaryPanel) {
                aiSummaryPanel.hidden = true;
                aiSummaryPanel.textContent = "";
              }
              aiSummaryButton.textContent = "AI 生成决策摘要";
            }
            showAiNote(error.message);
          } finally {
            aiSummaryButton.disabled = false;
          }
        });
      }

      const editConclusionButton = document.getElementById(
        "editConclusionButton"
      );
      if (editConclusionButton) {
        const conclusionForm = document.getElementById("conclusionForm");
        const conclusionText = document.getElementById("conclusionText");
        const conclusionShare = document.getElementById("conclusionShare");
        const saveConclusionButton = document.getElementById(
          "saveConclusionButton"
        );
        const cancelConclusionButton = document.getElementById(
          "cancelConclusionButton"
        );

        editConclusionButton.addEventListener("click", () => {
          conclusionForm.hidden = false;
          editConclusionButton.hidden = true;
          conclusionText.value = topic.conclusion ? topic.conclusion.text : "";
          if (conclusionShare) {
            conclusionShare.checked = topic.conclusion
              ? Boolean(topic.conclusion.shared)
              : Boolean(topic.document);
          }
          conclusionText.focus();
        });

        cancelConclusionButton.addEventListener("click", () => {
          conclusionForm.hidden = true;
          editConclusionButton.hidden = false;
        });

        saveConclusionButton.addEventListener("click", async () => {
          const text = conclusionText.value.trim();
          if (!text) {
            alert("请填写最终结论");
            return;
          }
          saveConclusionButton.disabled = true;
          try {
            await apiRequest(`/api/qa/topics/${topicId}/conclusion`, {
              method: "POST",
              body: JSON.stringify({
                text,
                share_to_document: Boolean(
                  conclusionShare && conclusionShare.checked
                ),
              }),
            });
            await reload();
          } catch (error) {
            alert(error.message);
            saveConclusionButton.disabled = false;
          }
        });
      }

      const editCategoryButton = document.getElementById("editCategoryButton");
      if (editCategoryButton) {
        const categorySpan = document.getElementById("topicCategory");
        const categorySelect = document.getElementById("categorySelect");
        const saveCategoryButton = document.getElementById("saveCategoryButton");

        editCategoryButton.addEventListener("click", async () => {
          if (!categorySelect.dataset.loaded) {
            try {
              const categories = await apiRequest("/api/qa/categories");
              categorySelect.innerHTML =
                '<option value="">未分类</option>' +
                categories
                  .map(
                    (category) =>
                      `<option value="${category.id}">${escapeHtml(
                        category.name
                      )}</option>`
                  )
                  .join("");
              categorySelect.dataset.loaded = "1";
            } catch (error) {
              alert(error.message);
              return;
            }
          }
          categorySelect.value = topic.category
            ? String(topic.category.id)
            : "";
          categorySpan.hidden = true;
          editCategoryButton.hidden = true;
          categorySelect.hidden = false;
          saveCategoryButton.hidden = false;
        });

        saveCategoryButton.addEventListener("click", async () => {
          saveCategoryButton.disabled = true;
          try {
            await apiRequest(`/api/qa/topics/${topicId}`, {
              method: "PATCH",
              body: JSON.stringify({
                category_id: categorySelect.value
                  ? Number(categorySelect.value)
                  : null,
              }),
            });
            await reload();
          } catch (error) {
            alert(error.message);
            saveCategoryButton.disabled = false;
          }
        });
      }

      const editDocumentButton = document.getElementById("editDocumentButton");
      if (editDocumentButton) {
        const topicDocumentSpan = document.getElementById("topicDocument");
        const documentEditor = document.getElementById("documentEditor");
        const documentSelect = document.getElementById("documentSelect");
        const versionSelect = document.getElementById("versionSelect");
        const saveDocumentButton = document.getElementById("saveDocumentButton");
        const cancelDocumentButton = document.getElementById(
          "cancelDocumentButton"
        );

        async function loadVersionOptions(documentId, preselect) {
          versionSelect.innerHTML = '<option value="">不指定版本</option>';
          if (!documentId) {
            versionSelect.hidden = true;
            return;
          }
          try {
            const versions = await apiRequest(
              `/api/documents/${encodeURIComponent(documentId)}/versions`
            );
            versionSelect.innerHTML =
              '<option value="">不指定版本</option>' +
              versions
                .map(
                  (version) =>
                    `<option value="${version.id}">v${version.version_number}（${escapeHtml(
                      version.filename
                    )}）</option>`
                )
                .join("");
            if (preselect) {
              versionSelect.value = String(preselect);
            }
            versionSelect.hidden = false;
          } catch (_) {
            versionSelect.hidden = true;
          }
        }

        editDocumentButton.addEventListener("click", async () => {
          if (!documentSelect.dataset.loaded) {
            try {
              const documents = await apiRequest("/api/documents");
              documentSelect.innerHTML =
                '<option value="">不关联文档</option>' +
                documents
                  .map(
                    (doc) =>
                      `<option value="${doc.id}">${escapeHtml(doc.title)}</option>`
                  )
                  .join("");
              documentSelect.dataset.loaded = "1";
            } catch (error) {
              alert(error.message);
              return;
            }
          }
          documentSelect.value = topic.document
            ? String(topic.document.id)
            : "";
          await loadVersionOptions(
            documentSelect.value,
            topic.version ? topic.version.id : null
          );
          topicDocumentSpan.hidden = true;
          editDocumentButton.hidden = true;
          documentEditor.hidden = false;
        });

        documentSelect.addEventListener("change", () => {
          loadVersionOptions(documentSelect.value);
        });

        cancelDocumentButton.addEventListener("click", () => {
          reload();
        });

        saveDocumentButton.addEventListener("click", async () => {
          saveDocumentButton.disabled = true;
          const payload = {
            document_id: documentSelect.value
              ? Number(documentSelect.value)
              : null,
          };
          if (documentSelect.value && versionSelect.value) {
            payload.version_id = Number(versionSelect.value);
          }
          try {
            await apiRequest(`/api/qa/topics/${topicId}`, {
              method: "PATCH",
              body: JSON.stringify(payload),
            });
            await reload();
          } catch (error) {
            alert(error.message);
            saveDocumentButton.disabled = false;
          }
        });
      }

      const closeButton = document.getElementById("closeTopicButton");
      if (closeButton) {
        closeButton.addEventListener("click", async () => {
          if (!window.confirm("确定结束这个话题吗？结束后所有人都不能再发言。")) {
            return;
          }
          closeButton.disabled = true;
          try {
            await apiRequest(`/api/qa/topics/${topicId}`, {
              method: "PATCH",
              body: JSON.stringify({ status: "closed" }),
            });
            await reload();
          } catch (error) {
            alert(error.message);
            closeButton.disabled = false;
          }
        });
      }

      if (topic.status === "closed") {
        statementForm.style.display = "none";
        const notice = document.getElementById("statementNotice");
        if (notice) {
          notice.hidden = false;
          notice.textContent = topic.expired
            ? "本话题已到设定的结束时间，已自动结束，不能再发言。"
            : "本话题已结束，不能再发言。";
        }
      } else {
        statementForm.style.display = "";
        const notice = document.getElementById("statementNotice");
        if (notice) {
          notice.hidden = true;
        }
      }
      // 提示元素在 innerHTML 里重建过，刷新时间要在这之后再写
      markLiveHint();
    } catch (error) {
      showPageMessage("detail", error.message, true);
    }
  }

  let replyParentId = null;
  let replyQuoteId = null;

  function resetReplyContext() {
    replyParentId = null;
    replyQuoteId = null;
    const replyContext = document.getElementById("replyContext");
    const replyContextText = document.getElementById("replyContextText");
    const quotePreview = document.getElementById("quotePreview");
    if (!replyContext) {
      return;
    }
    replyContext.hidden = true;
    replyContextText.textContent = "";
    quotePreview.hidden = true;
    quotePreview.textContent = "";
  }

  function startReply(statement, quote) {
    replyParentId = statement.id;
    replyQuoteId = quote ? statement.id : null;
    const replyContext = document.getElementById("replyContext");
    const replyContextText = document.getElementById("replyContextText");
    const quotePreview = document.getElementById("quotePreview");
    if (!replyContext) {
      return;
    }
    replyContext.hidden = false;
    replyContextText.textContent = quote
      ? `引用 @${statement.author.name}：`
      : `回复 @${statement.author.name}：`;
    quotePreview.hidden = !quote;
    if (quote) {
      quotePreview.textContent = statement.content;
    }
    document.getElementById("statementContent").focus();
  }

  function buildTimelineTree(statements) {
    const roots = [];
    const byId = new Map();
    statements.forEach((statement) => {
      byId.set(statement.id, { ...statement, children: [] });
    });
    byId.forEach((node) => {
      if (node.parent_id && byId.has(node.parent_id)) {
        byId.get(node.parent_id).children.push(node);
      } else {
        roots.push(node);
      }
    });
    return roots;
  }

  function renderTimeline(statements) {
    const timeline = document.getElementById("timeline");
    if (!timeline) {
      return;
    }

    const roots = buildTimelineTree(statements || []);
    const rows = [];
    (function walk(nodes, depth) {
      nodes.forEach((node) => {
        rows.push({ node, depth });
        walk(node.children || [], depth + 1);
      });
    })(roots, 0);

    timeline.innerHTML = rows.length
      ? rows
          .map(({ node, depth }) => {
            const replyLabel = node.parent
              ? `<span class="reply-to">回复 @${escapeHtml(
                  node.parent.author.name
                )}</span>`
              : "";
            const quoteBlock = node.quoted
              ? `
                <blockquote class="quote-preview quote-in-timeline">
                  <strong>${escapeHtml(node.quoted.author.name)}：</strong>
                  ${escapeHtml(node.quoted.content)}
                </blockquote>
              `
              : "";
            const isHidden = Boolean(node.hidden);
            const hiddenBadge = isHidden
              ? '<span class="hidden-badge">已隐藏</span>'
              : "";
            const hiddenNote = isHidden
              ? `<p class="timeline-hidden-note">已隐藏（不计入汇总）${
                  node.hidden_by
                    ? " · 由 " + escapeHtml(node.hidden_by.name)
                    : ""
                }${node.hidden_at ? " · " + formatTime(node.hidden_at) : ""}${
                  node.hidden_reason
                    ? " · 原因：" + escapeHtml(node.hidden_reason)
                    : ""
                }</p>`
              : "";
            // 隐藏/恢复只对管理员开放；被隐藏的发言不提供回复和引用
            const interactionActions = isHidden
              ? ""
              : `<button class="link-btn" type="button" data-reply="${node.id}">回复</button>
                 <button class="link-btn" type="button" data-quote="${node.id}">引用</button>`;
            const moderationAction =
              user.role === "admin"
                ? isHidden
                  ? `<button class="link-btn" type="button" data-restore="${node.id}">恢复</button>`
                  : `<button class="link-btn link-btn-danger" type="button" data-hide="${node.id}">隐藏</button>`
                : "";
            // 非管理员只能举报别人的、且未被隐藏的发言
            const reportAction =
              !isHidden &&
              user.role !== "admin" &&
              node.author.id !== user.id
                ? `<button class="link-btn" type="button" data-report="${node.id}">举报</button>`
                : "";
            return `
              <div class="timeline-item${isHidden ? " is-hidden" : ""}" style="margin-left:${Math.min(
                depth,
                6
              ) * 18}px">
                <div class="timeline-head">
                  <strong>${escapeHtml(node.author.name)}</strong>
                  ${positionBadge(node.position)}
                  ${replyLabel}
                  ${hiddenBadge}
                  <span class="timeline-time">${formatTime(
                    node.created_at
                  )}</span>
                </div>
                ${quoteBlock}
                ${hiddenNote}
                <p class="timeline-content">${escapeHtml(node.content)}</p>
                <div class="timeline-actions">
                  ${interactionActions}
                  ${reportAction}
                  ${moderationAction}
                </div>
              </div>
            `;
          })
          .join("")
      : '<div class="muted">还没有发言，来发第一条吧。</div>';

    timeline.querySelectorAll('[data-reply]').forEach((button) => {
      button.addEventListener("click", () => {
        const statement = (statements || []).find(
          (item) => String(item.id) === String(button.dataset.reply)
        );
        if (statement) {
          startReply(statement, false);
        }
      });
    });

    timeline.querySelectorAll('[data-quote]').forEach((button) => {
      button.addEventListener("click", () => {
        const statement = (statements || []).find(
          (item) => String(item.id) === String(button.dataset.quote)
        );
        if (statement) {
          startReply(statement, true);
        }
      });
    });

    timeline.querySelectorAll("[data-hide]").forEach((button) => {
      button.addEventListener("click", async () => {
        const reason = window.prompt("隐藏这条发言的原因（可留空）", "");
        if (reason === null) {
          return;
        }
        try {
          await apiRequest(
            `/api/qa/topics/${topicId}/statements/${button.dataset.hide}`,
            {
              method: "PATCH",
              body: JSON.stringify({ hidden: true, reason }),
            }
          );
          await reload();
        } catch (error) {
          alert(error.message);
        }
      });
    });

    timeline.querySelectorAll("[data-restore]").forEach((button) => {
      button.addEventListener("click", async () => {
        if (
          !window.confirm("恢复这条发言？恢复后会重新出现在时间线并计入汇总。")
        ) {
          return;
        }
        try {
          await apiRequest(
            `/api/qa/topics/${topicId}/statements/${button.dataset.restore}`,
            {
              method: "PATCH",
              body: JSON.stringify({ hidden: false }),
            }
          );
          await reload();
        } catch (error) {
          alert(error.message);
        }
      });
    });

    timeline.querySelectorAll("[data-report]").forEach((button) => {
      button.addEventListener("click", () => {
        const statement = (statements || []).find(
          (item) => String(item.id) === String(button.dataset.report)
        );
        if (!statement) {
          return;
        }
        reportTargetId = statement.id;
        const form = document.getElementById("reportForm");
        const target = document.getElementById("reportTarget");
        const reason = document.getElementById("reportReason");
        if (target) {
          target.textContent = `举报 ${statement.author.name} 的发言`;
        }
        if (reason) {
          reason.value = "";
        }
        if (form) {
          form.hidden = false;
          form.scrollIntoView({ block: "center", behavior: "smooth" });
        }
        if (reason) {
          reason.focus();
        }
      });
    });
  }

  const cancelReplyButton = document.getElementById("cancelReplyButton");
  if (cancelReplyButton) {
    cancelReplyButton.addEventListener("click", resetReplyContext);
  }

  statementForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const content = document.getElementById("statementContent").value.trim();
    const position = document.getElementById("statementPosition").value;
    const submitButton = statementForm.querySelector('button[type="submit"]');

    if (!content) {
      alert("请填写发言内容");
      return;
    }

    const payload = { content, position };
    if (replyParentId) {
      payload.parent_id = replyParentId;
    }
    if (replyQuoteId) {
      payload.quote_statement_id = replyQuoteId;
    }

    submitButton.disabled = true;
    submitButton.textContent = "提交中...";
    try {
      await apiRequest(`/api/qa/topics/${topicId}/statements`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      document.getElementById("statementContent").value = "";
      resetReplyContext();
      // 新发言会让服务端把已落库的 AI 摘要标记为过期，reload 后会提示重新生成
      await reload();
    } catch (error) {
      alert(error.message);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "发表";
    }
  });

  await reload();
  startPolling();
}

async function initNewTopic() {
  await requireUser();
  const form = document.getElementById("newTopicForm");
  const endsAtInput = document.getElementById("endsAt");
  const categorySelect = document.getElementById("category");

  try {
    const categories = await apiRequest("/api/qa/categories");
    categorySelect.innerHTML =
      '<option value="">未分类</option>' +
      categories
        .map(
          (category) =>
            `<option value="${category.id}">${escapeHtml(category.name)}</option>`
        )
        .join("");
  } catch (_) {
    // 分类加载失败时保留“未分类”选项
  }

  const relatedDocument = document.getElementById("relatedDocument");
  const relatedVersionWrap = document.getElementById("relatedVersionWrap");
  const relatedVersion = document.getElementById("relatedVersion");

  async function loadVersions(documentId, preselect) {
    relatedVersion.innerHTML = '<option value="">不指定版本</option>';
    if (!documentId) {
      relatedVersionWrap.hidden = true;
      return;
    }
    try {
      const versions = await apiRequest(
        `/api/documents/${encodeURIComponent(documentId)}/versions`
      );
      relatedVersion.innerHTML =
        '<option value="">不指定版本</option>' +
        versions
          .map(
            (version) =>
              `<option value="${version.id}">v${version.version_number}（${escapeHtml(
                version.filename
              )}）</option>`
          )
          .join("");
      if (preselect) {
        relatedVersion.value = String(preselect);
      }
      relatedVersionWrap.hidden = false;
    } catch (_) {
      relatedVersionWrap.hidden = true;
    }
  }

  try {
    const documents = await apiRequest("/api/documents");
    relatedDocument.innerHTML =
      '<option value="">不关联文档</option>' +
      documents
        .map(
          (doc) => `<option value="${doc.id}">${escapeHtml(doc.title)}</option>`
        )
        .join("");
  } catch (_) {
    // 文档加载失败时保留“不关联文档”选项
  }

  // 从文档详情页跳转过来时预选对应文档
  const presetDocumentId = qs("document_id");
  if (presetDocumentId) {
    relatedDocument.value = presetDocumentId;
    if (relatedDocument.value) {
      await loadVersions(presetDocumentId);
    }
  }

  relatedDocument.addEventListener("change", () => {
    loadVersions(relatedDocument.value);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = document.getElementById("title").value.trim();
    const description = document.getElementById("description").value.trim();
    const endsAtLocal = endsAtInput ? endsAtInput.value : "";
    const submitButton = form.querySelector('button[type="submit"]');

    if (!title) {
      alert("请填写话题标题");
      return;
    }

    const payload = { title, description };
    const categoryId = categorySelect.value;
    if (categoryId) {
      payload.category_id = Number(categoryId);
    }
    const documentId = relatedDocument.value;
    if (documentId) {
      payload.document_id = Number(documentId);
      if (relatedVersion.value) {
        payload.version_id = Number(relatedVersion.value);
      }
    }
    if (endsAtLocal) {
      const parsed = new Date(endsAtLocal);
      if (Number.isNaN(parsed.getTime())) {
        alert("结束时间格式不正确");
        return;
      }
      payload.ends_at = parsed.toISOString();
    }

    submitButton.disabled = true;
    submitButton.textContent = "创建中...";
    try {
      const topic = await apiRequest("/api/qa/topics", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      window.location.href = `topic.html?id=${topic.id}`;
    } catch (error) {
      alert(error.message);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "发起话题";
    }
  });
}

async function initManageQaCategories() {
  const user = await requireUser();
  if (user.role !== "admin") {
    window.location.href = "index.html";
    return;
  }

  const form = document.getElementById("categoryForm");
  const formTitle = document.getElementById("categoryFormTitle");
  const nameInput = document.getElementById("categoryName");
  const sortInput = document.getElementById("sortOrder");
  const submitButton = document.getElementById("categorySubmitButton");
  const cancelButton = document.getElementById("categoryCancelButton");
  const listContainer = document.getElementById("categoryList");

  let editingId = null;
  let categories = [];

  function resetForm() {
    editingId = null;
    formTitle.textContent = "新建分类";
    submitButton.textContent = "新建分类";
    cancelButton.hidden = true;
    nameInput.value = "";
    sortInput.value = "0";
  }

  function bindListActions() {
    listContainer.querySelectorAll('[data-action="edit"]').forEach((button) => {
      button.addEventListener("click", () => {
        const category = categories.find(
          (item) => String(item.id) === String(button.dataset.id)
        );
        if (!category) {
          return;
        }
        editingId = category.id;
        formTitle.textContent = "编辑分类";
        submitButton.textContent = "保存修改";
        cancelButton.hidden = false;
        nameInput.value = category.name;
        sortInput.value = category.sort_order;
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    });

    listContainer
      .querySelectorAll('[data-action="delete"]')
      .forEach((button) => {
        button.addEventListener("click", async () => {
          const category = categories.find(
            (item) => String(item.id) === String(button.dataset.id)
          );
          if (!category) {
            return;
          }
          if (
            !window.confirm(
              `确定删除分类「${category.name}」吗？删除后不可恢复。`
            )
          ) {
            return;
          }
          try {
            await apiRequest(`/api/qa/categories/${category.id}`, {
              method: "DELETE",
            });
            if (editingId === category.id) {
              resetForm();
            }
            await reload();
          } catch (error) {
            alert(error.message);
          }
        });
      });
  }

  async function reload() {
    try {
      categories = await apiRequest("/api/qa/categories");
      listContainer.innerHTML = categories.length
        ? `
          <table class="table">
            <thead>
              <tr>
                <th>分类名称</th>
                <th>排序值</th>
                <th>话题数</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              ${categories
                .map(
                  (category) => `
                    <tr>
                      <td>${escapeHtml(category.name)}</td>
                      <td>${category.sort_order}</td>
                      <td>${category.topic_count}</td>
                      <td>${formatTime(category.created_at)}</td>
                      <td class="actions">
                        <button class="btn btn-outline btn-sm" data-action="edit" data-id="${category.id}" type="button">编辑</button>
                        <button class="btn btn-danger btn-sm" data-action="delete" data-id="${category.id}" type="button">删除</button>
                      </td>
                    </tr>
                  `
                )
                .join("")}
            </tbody>
          </table>
        `
        : '<div class="muted">还没有分类，先在上方新建一个。</div>';
      bindListActions();
    } catch (error) {
      listContainer.innerHTML = `<div class="notice">${escapeHtml(
        error.message
      )}</div>`;
    }
  }

  cancelButton.addEventListener("click", resetForm);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = nameInput.value.trim();
    const sortOrder = Number(sortInput.value) || 0;
    if (!name) {
      alert("请填写分类名称");
      return;
    }

    submitButton.disabled = true;
    const body = JSON.stringify({ name, sort_order: sortOrder });
    try {
      if (editingId) {
        await apiRequest(`/api/qa/categories/${editingId}`, {
          method: "PATCH",
          body,
        });
      } else {
        await apiRequest("/api/qa/categories", {
          method: "POST",
          body,
        });
      }
      resetForm();
      await reload();
    } catch (error) {
      alert(error.message);
    } finally {
      submitButton.disabled = false;
    }
  });

  await reload();
}

async function initNotifications() {
  await requireUser();
  const list = document.getElementById("notificationList");
  const summary = document.getElementById("notificationSummary");
  const markAllButton = document.getElementById("markAllReadButton");

  async function reload() {
    try {
      const data = await apiRequest("/api/qa/notifications");
      const items = data.items || [];
      if (summary) {
        summary.textContent = items.length
          ? `共 ${items.length} 条 · 未读 ${data.unread} 条`
          : "暂无通知";
      }
      if (markAllButton) {
        markAllButton.disabled = !data.unread;
      }
      list.innerHTML = items.length
        ? `<ul class="notification-list">${items
            .map(
              (item) => `
                <li class="notification-item${item.read ? "" : " is-unread"}">
                  <div class="notification-head">
                    <span class="notification-kind">${escapeHtml(
                      NOTIFICATION_KIND_LABELS[item.kind] || "通知"
                    )}</span>
                    <span class="muted">${formatTime(item.created_at)}</span>
                  </div>
                  <p class="notification-message">${escapeHtml(item.message)}</p>
                  ${
                    item.topic_id
                      ? `<a class="btn btn-outline btn-sm" href="topic.html?id=${item.topic_id}">查看话题</a>`
                      : ""
                  }
                </li>
              `
            )
            .join("")}</ul>`
        : '<div class="muted">还没有通知。</div>';
    } catch (error) {
      list.innerHTML = `<div class="notice">${escapeHtml(error.message)}</div>`;
    }
  }

  if (markAllButton) {
    markAllButton.addEventListener("click", async () => {
      try {
        await apiRequest("/api/qa/notifications/read", { method: "POST" });
        await reload();
        refreshTopbarBadges();
      } catch (error) {
        alert(error.message);
      }
    });
  }

  await reload();
}

async function initReports() {
  const user = await requireUser();
  if (user.role !== "admin") {
    window.location.href = "index.html";
    return;
  }

  const list = document.getElementById("reportList");
  const summary = document.getElementById("reportSummary");

  function bindActions() {
    list.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.action;
        const reportId = button.dataset.id;
        const confirmText =
          action === "hide"
            ? "隐藏这条发言？隐藏后普通用户看不到，也不计入汇总。"
            : "驳回这条举报？发言将保持可见。";
        if (!window.confirm(confirmText)) {
          return;
        }
        button.disabled = true;
        try {
          await apiRequest(`/api/qa/reports/${reportId}`, {
            method: "PATCH",
            body: JSON.stringify({ action }),
          });
          await reload();
          refreshTopbarBadges();
        } catch (error) {
          alert(error.message);
          button.disabled = false;
        }
      });
    });
  }

  async function reload() {
    try {
      const data = await apiRequest("/api/qa/reports?status=pending");
      const items = data.items || [];
      if (summary) {
        summary.textContent = items.length
          ? `待处理 ${data.pending} 条`
          : "没有待处理的举报";
      }
      list.innerHTML = items.length
        ? items
            .map(
              (item) => `
                <div class="report-card">
                  <div class="report-head">
                    <a href="topic.html?id=${item.topic_id}">${escapeHtml(
                      item.topic_title
                    )}</a>
                    <span class="muted">${escapeHtml(
                      item.reporter ? item.reporter.name : "未知"
                    )} 举报 · ${formatTime(item.created_at)}</span>
                  </div>
                  <p class="report-reason">举报理由：${escapeHtml(item.reason)}</p>
                  <blockquote class="quote-preview">
                    <strong>${escapeHtml(
                      item.statement && item.statement.author
                        ? item.statement.author.name
                        : "未知"
                    )}：</strong>
                    ${escapeHtml(item.statement ? item.statement.content : "")}
                  </blockquote>
                  <div class="actions">
                    <button class="btn btn-primary btn-sm" data-action="hide" data-id="${item.id}" type="button">隐藏该发言并结案</button>
                    <button class="btn btn-outline btn-sm" data-action="dismiss" data-id="${item.id}" type="button">驳回举报</button>
                  </div>
                </div>
              `
            )
            .join("")
        : '<div class="muted">当前没有待处理的举报。</div>';
      bindActions();
    } catch (error) {
      list.innerHTML = `<div class="notice">${escapeHtml(error.message)}</div>`;
    }
  }

  await reload();
}

document.addEventListener("DOMContentLoaded", async () => {
  const page = document.body.dataset.page;
  try {
    if (page === "topics") {
      await initTopicList();
    }
    if (page === "topic") {
      await initTopicDetail();
    }
    if (page === "newTopic") {
      await initNewTopic();
    }
    if (page === "qaCategories") {
      await initManageQaCategories();
    }
    if (page === "notifications") {
      await initNotifications();
    }
    if (page === "reports") {
      await initReports();
    }
  } catch (error) {
    if (error.status !== 401) {
      alert(error.message);
    }
  }
});
