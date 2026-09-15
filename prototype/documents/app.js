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

  if (response.status === 401) {
    if (redirectOn401 && document.body.dataset.page !== "login") {
      window.location.href = "index.html";
    }
    const error = new Error("请先登录");
    error.status = 401;
    throw error;
  }

  let payload = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    payload = await response.json();
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
    // The local state is cleared even if the server session already expired.
  }
  currentUser = null;
  window.location.href = "index.html";
}

function renderTopbar(user) {
  document.querySelectorAll("#topbar").forEach((node) => {
    node.innerHTML = `
      <span class="user-pill">${escapeHtml(user.name)} · ${
        user.role === "admin" ? "管理员" : "教师"
      }</span>
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
    <div class="card ${isError ? "notice" : "muted"}">
      ${escapeHtml(message)}
    </div>
  `;
}

function initLogin() {
  const form = document.getElementById("loginForm");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    const submitButton = form.querySelector('button[type="submit"]');

    if (!username || !password) {
      alert("请填写工号和密码");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "登录中...";
    try {
      await apiRequest(
        "/api/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ username, password }),
        },
        { redirectOn401: false }
      );
      window.location.href = "categories.html";
    } catch (error) {
      alert(error.message);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "登录";
    }
  });
}

async function initCategories() {
  const user = await requireUser();
  const container = document.getElementById("categoryList");

  try {
    const categories = await apiRequest("/api/categories");
    container.innerHTML = categories.length
      ? categories
          .map(
            (category) => `
              <a class="card category-card" href="documents.html?category_id=${category.id}">
                <h3>${escapeHtml(category.name)}</h3>
                <p>${escapeHtml(category.description || "查看该分类下的文档")}</p>
                <span class="count">${category.document_count} 份文档</span>
              </a>
            `
          )
          .join("")
      : '<div class="card muted">暂无分类</div>';
  } catch (error) {
    showPageMessage("categoryList", error.message, true);
  }
}

async function initDocuments() {
  await requireUser();
  const categoryId = qs("category_id") || "";
  const filter = document.getElementById("categoryFilter");
  const list = document.getElementById("documentList");

  try {
    const categories = await apiRequest("/api/categories");
    filter.innerHTML =
      '<option value="">全部分类</option>' +
      categories
        .map(
          (category) =>
            `<option value="${category.id}" ${
              String(category.id) === categoryId ? "selected" : ""
            }>${escapeHtml(category.name)}</option>`
        )
        .join("");

    const path = categoryId
      ? `/api/documents?category_id=${encodeURIComponent(categoryId)}`
      : "/api/documents";
    const documents = await apiRequest(path);

    list.innerHTML = documents.length
      ? documents
          .map((document) => {
            const current = document.current_version;
            return `
              <tr>
                <td><a href="document-detail.html?id=${document.id}">${escapeHtml(
                  document.title
                )}</a></td>
                <td>${escapeHtml(document.category.name)}</td>
                <td>${escapeHtml(document.owner.name)}</td>
                <td>v${current ? current.version_number : 0}</td>
                <td>${formatTime(document.updated_at)}</td>
              </tr>
            `;
          })
          .join("")
      : '<tr><td colspan="5" class="muted">该分类暂无文档</td></tr>';
  } catch (error) {
    list.innerHTML = `<tr><td colspan="5" class="notice">${escapeHtml(
      error.message
    )}</td></tr>`;
  }

  filter.addEventListener("change", () => {
    const next = new URLSearchParams(window.location.search);
    if (filter.value) {
      next.set("category_id", filter.value);
    } else {
      next.delete("category_id");
    }
    window.location.search = next.toString();
  });
}

async function initDocumentDetail() {
  const user = await requireUser();
  const documentId = qs("id");
  const container = document.getElementById("detail");

  try {
    const document = await apiRequest(`/api/documents/${documentId}`);
    const current = document.current_version;
    const canUpload =
      user.role === "admin" || user.id === document.owner.id;

    document.getElementById("pageTitle").textContent = document.title;
    container.innerHTML = `
      <div class="card">
        <dl class="detail-list">
          <dt>文档标题</dt><dd>${escapeHtml(document.title)}</dd>
          <dt>所属分类</dt><dd>${escapeHtml(document.category.name)}</dd>
          <dt>负责人</dt><dd>${escapeHtml(document.owner.name)}</dd>
          <dt>当前版本</dt><dd>v${current ? current.version_number : 0}</dd>
          <dt>最近更新</dt><dd>${formatTime(document.updated_at)}</dd>
          <dt>说明</dt><dd>${escapeHtml(document.description || "-")}</dd>
        </dl>
        <div class="actions">
          ${
            current
              ? `<a class="btn btn-primary" href="download.html?id=${document.id}&version_id=${current.id}">下载当前版本</a>`
              : ""
          }
          ${
            canUpload
              ? `<a class="btn btn-outline" href="upload-version.html?id=${document.id}">上传新版本</a>`
              : '<span class="notice" style="margin:0">你当前为只读权限，不能上传新版本</span>'
          }
          <a class="btn btn-outline" href="versions.html?id=${document.id}">查看历史版本</a>
        </div>
      </div>
    `;
  } catch (error) {
    showPageMessage("detail", error.message, true);
  }
}

async function initUpload() {
  await requireUser();
  const documentId = qs("id");
  const form = document.getElementById("uploadForm");
  const backLink = document.getElementById("backLink");

  try {
    const document = await apiRequest(`/api/documents/${documentId}`);
    document.getElementById("docTitle").textContent = document.title;
    backLink.href = `document-detail.html?id=${document.id}`;
  } catch (error) {
    showPageMessage("upload", error.message, true);
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const fileInput = document.getElementById("file");
    const changelog = document.getElementById("changelog").value.trim();
    const file = fileInput.files[0];

    if (!file) {
      alert("请选择文件");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("changelog", changelog);

    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = "上传中...";
    try {
      await apiRequest(`/api/documents/${documentId}/versions`, {
        method: "POST",
        body: formData,
      });
      window.location.href = `document-detail.html?id=${documentId}`;
    } catch (error) {
      alert(error.message);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "上传并生成新版本";
    }
  });
}

async function initVersions() {
  await requireUser();
  const documentId = qs("id");
  const container = document.getElementById("versions");

  try {
    const document = await apiRequest(`/api/documents/${documentId}`);
    const versions = await apiRequest(
      `/api/documents/${documentId}/versions`
    );
    document.getElementById("docTitle").textContent = document.title;
    container.innerHTML = versions.length
      ? versions
          .map(
            (version) => `
              <div class="card">
                <div class="toolbar">
                  <strong>v${version.version_number}</strong>
                  <a class="btn btn-outline" href="download.html?id=${document.id}&version_id=${version.id}">下载</a>
                </div>
                <dl class="detail-list">
                  <dt>文件名</dt><dd>${escapeHtml(version.filename)}</dd>
                  <dt>变更说明</dt><dd>${escapeHtml(version.changelog || "-")}</dd>
                  <dt>上传人</dt><dd>${escapeHtml(version.uploader.name)}</dd>
                  <dt>上传时间</dt><dd>${formatTime(version.created_at)}</dd>
                </dl>
              </div>
            `
          )
          .join("")
      : '<div class="card muted">暂无历史版本</div>';
  } catch (error) {
    showPageMessage("versions", error.message, true);
  }
}

async function initDownload() {
  await requireUser();
  const documentId = qs("id");
  const versionId = qs("version_id");
  const container = document.getElementById("download");

  try {
    const document = await apiRequest(`/api/documents/${documentId}`);
    const versions = await apiRequest(
      `/api/documents/${documentId}/versions`
    );
    const version = versions.find(
      (item) => String(item.id) === String(versionId)
    );
    if (!version) {
      throw new Error("版本不存在");
    }

    container.innerHTML = `
      <div class="card">
        <dl class="detail-list">
          <dt>文档标题</dt><dd>${escapeHtml(document.title)}</dd>
          <dt>文件名</dt><dd>${escapeHtml(version.filename)}</dd>
          <dt>版本号</dt><dd>v${version.version_number}</dd>
          <dt>上传人</dt><dd>${escapeHtml(version.uploader.name)}</dd>
        </dl>
        <div class="actions">
          <button class="btn btn-primary" id="confirmDownload" type="button">确认下载</button>
          <a class="btn btn-outline" href="document-detail.html?id=${document.id}">返回详情</a>
        </div>
      </div>
    `;
    document.getElementById("confirmDownload").addEventListener("click", () => {
      window.location.href = `/api/documents/${document.id}/versions/${version.id}/download`;
    });
  } catch (error) {
    showPageMessage("download", error.message, true);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const page = document.body.dataset.page;
  try {
    if (page === "login") {
      initLogin();
    }
    if (page === "categories") {
      await initCategories();
    }
    if (page === "documents") {
      await initDocuments();
    }
    if (page === "detail") {
      await initDocumentDetail();
    }
    if (page === "upload") {
      await initUpload();
    }
    if (page === "versions") {
      await initVersions();
    }
    if (page === "download") {
      await initDownload();
    }
  } catch (error) {
    if (error.status !== 401) {
      alert(error.message);
    }
  }
});
