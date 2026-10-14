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
  document.querySelectorAll("#topbar").forEach((node) => {
    node.innerHTML = `
      <nav class="admin-nav">
        <a href="../documents/index.html">文档管理</a>
        <a href="index.html">问答话题</a>
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
  return user;
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

async function initTopicList() {
  await requireUser();
  const container = document.getElementById("topicList");

  try {
    const topics = await apiRequest("/api/qa/topics");
    container.innerHTML = topics.length
      ? topics
          .map(
            (topic) => `
              <tr>
                <td><a href="topic.html?id=${topic.id}">${escapeHtml(
                  topic.title
                )}</a></td>
                <td>${escapeHtml(topic.creator.name)}</td>
                <td>${statusBadge(topic.status)}</td>
                <td>${topic.statement_count}</td>
                <td>${topic.speaker_count}</td>
                <td>${formatTime(topic.latest_statement_at || topic.updated_at)}</td>
              </tr>
            `
          )
          .join("")
      : '<tr><td colspan="6" class="muted">还没有话题，点右上角「发起话题」开始讨论</td></tr>';
  } catch (error) {
    container.innerHTML = `<tr><td colspan="6" class="notice">${escapeHtml(
      error.message
    )}</td></tr>`;
  }
}

function renderSummary(summary) {
  const total = summary.statement_count || 0;
  const agree = summary.positions?.agree || 0;
  const disagree = summary.positions?.disagree || 0;
  const neutral = summary.positions?.neutral || 0;
  const consensus = summary.consensus_reached
    ? '<span class="notice notice-ok summary-verdict">已形成初步统一意见</span>'
    : '<span class="notice summary-verdict">意见尚未统一</span>';

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
    ${consensus}
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

  async function reload() {
    try {
      topic = await apiRequest(`/api/qa/topics/${topicId}`);
      document.getElementById("pageTitle").textContent = topic.title;

      const canClose =
        topic.status === "open" &&
        (user.role === "admin" || user.id === topic.creator.id);

      container.innerHTML = `
        <div class="card">
          <dl class="detail-list">
            <dt>发起人</dt><dd>${escapeHtml(topic.creator.name)}</dd>
            <dt>状态</dt><dd>${statusBadge(topic.status)}</dd>
            <dt>结束时间</dt><dd>${
              topic.ends_at ? formatTime(topic.ends_at) : "未设置"
            }</dd>
            <dt>创建时间</dt><dd>${formatTime(topic.created_at)}</dd>
            <dt>说明</dt><dd>${escapeHtml(topic.description || "-")}</dd>
          </dl>
          <div class="actions">
            ${
              canClose
                ? '<button class="btn btn-outline" id="closeTopicButton" type="button">结束话题</button>'
                : ""
            }
            <a class="btn btn-outline" href="index.html">返回话题列表</a>
          </div>
        </div>

        <section class="card summary-card">
          <h2>意见汇总</h2>
          ${renderSummary(topic.summary || {})}
        </section>

        <section class="card">
          <h2>讨论时间线</h2>
          <div id="timeline" class="timeline"></div>
        </section>
      `;

      renderTimeline(topic.statements || []);

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
    } catch (error) {
      showPageMessage("detail", error.message, true);
    }
  }

  function renderTimeline(statements) {
    const timeline = document.getElementById("timeline");
    if (!timeline) {
      return;
    }
    timeline.innerHTML = statements.length
      ? statements
          .map(
            (statement) => `
              <div class="timeline-item">
                <div class="timeline-head">
                  <strong>${escapeHtml(statement.author.name)}</strong>
                  ${positionBadge(statement.position)}
                  <span class="timeline-time">${formatTime(
                    statement.created_at
                  )}</span>
                </div>
                <p class="timeline-content">${escapeHtml(statement.content)}</p>
              </div>
            `
          )
          .join("")
      : '<div class="muted">还没有发言，来发第一条吧。</div>';
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

    submitButton.disabled = true;
    submitButton.textContent = "提交中...";
    try {
      await apiRequest(`/api/qa/topics/${topicId}/statements`, {
        method: "POST",
        body: JSON.stringify({ content, position }),
      });
      document.getElementById("statementContent").value = "";
      await reload();
    } catch (error) {
      alert(error.message);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "发表";
    }
  });

  await reload();
}

async function initNewTopic() {
  await requireUser();
  const form = document.getElementById("newTopicForm");
  const endsAtInput = document.getElementById("endsAt");

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
  } catch (error) {
    if (error.status !== 401) {
      alert(error.message);
    }
  }
});
