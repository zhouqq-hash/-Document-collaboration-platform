let currentUser = null;

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

function indexToLetters(index) {
  let number = index + 1;
  let letters = "";
  while (number > 0) {
    const remainder = (number - 1) % 26;
    letters = String.fromCharCode(65 + remainder) + letters;
    number = Math.floor((number - 1) / 26);
  }
  return letters;
}

function loginPageUrl() {
  return `/documents/index.html?next=${encodeURIComponent(
    window.location.pathname + window.location.search
  )}`;
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
      window.location.href = loginPageUrl();
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
    // 会话已过期时也照常清空本地状态。
  }
  currentUser = null;
  window.location.href = "/documents/index.html";
}

function renderTopbar(user) {
  document.querySelectorAll("#topbar").forEach((node) => {
    node.innerHTML = `
      <div class="topbar-user">
        <span class="user-pill">${escapeHtml(user.name)} · ${
          user.role === "admin" ? "管理员" : "教师"
        }</span>
        <button class="btn-quiet" id="logoutButton" type="button">退出</button>
      </div>
    `;
    node.querySelector("#logoutButton").addEventListener("click", logout);
  });
}

function toast(message, kind = "info") {
  const box = document.getElementById("toastBox");
  if (!box) {
    return;
  }
  const item = document.createElement("div");
  item.className = `toast toast-${kind}`;
  item.textContent = message;
  box.appendChild(item);
  setTimeout(() => item.remove(), 3200);
}

const CHANGE_KIND_LABELS = {
  cell_update: "单元格编辑",
  row_add: "新增行",
  row_delete: "删除行",
  rows_delete: "批量删除行",
  column_add: "新增列",
  column_update: "调整列",
  column_delete: "删除列",
  columns_delete: "批量删除列",
  rename: "修改信息",
  rollback: "版本回滚",
  import: "导入文件",
};

function changeSummary(change) {
  if (change.kind === "cell_update") {
    return `${change.column_name || change.column_key}:「${change.old_value}」→「${change.new_value}」`;
  }
  if (change.kind === "row_add") {
    return `新增一行（${change.row_key}）`;
  }
  if (change.kind === "row_delete") {
    return `删除一行（${change.row_key}）`;
  }
  if (change.kind === "rows_delete") {
    return `删除 ${change.detail?.deleted_count ?? change.detail?.row_keys?.length ?? 0} 行`;
  }
  if (change.kind === "column_add") {
    return `新增列「${change.column_name}」`;
  }
  if (change.kind === "column_update") {
    const nameChange =
      change.detail?.name_from !== change.detail?.name_to
        ? `名称由「${change.detail?.name_from}」改为「${change.detail?.name_to}」`
        : null;
    const widthChange =
      change.detail?.width_from !== change.detail?.width_to
        ? `列宽由 ${change.detail?.width_from ?? "-"} 调为 ${change.detail?.width_to}`
        : null;
    return [nameChange, widthChange].filter(Boolean).join("；");
  }
  if (change.kind === "column_delete") {
    return `删除列「${change.column_name}」`;
  }
  if (change.kind === "columns_delete") {
    const names = (change.detail?.columns || []).map((item) => item.name).join("、");
    return `删除 ${change.detail?.deleted_count ?? 0} 列：${names}`;
  }
  if (change.kind === "rollback") {
    return `从版本 ${change.detail?.from_version ?? change.old_value} 回滚到版本 ${change.detail?.to_version ?? change.new_value}`;
  }
  if (change.kind === "import") {
    const locked = change.detail?.locked_formula_count || 0;
    return `导入 ${change.detail?.filename || "文件"}：${change.detail?.row_count ?? 0} 行、${
      change.detail?.column_count ?? 0
    } 列${locked ? `，锁定 ${locked} 个公式` : ""}`;
  }
  if (change.kind === "rename") {
    return `名称由「${change.old_value}」改为「${change.new_value}」`;
  }
  return change.kind;
}
