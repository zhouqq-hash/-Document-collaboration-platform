const STATE_KEY = "docPrototypeState";
const USER_KEY = "docPrototypeUser";

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function loadState() {
  const saved = localStorage.getItem(STATE_KEY);
  if (saved) {
    try {
      return JSON.parse(saved);
    } catch (_) {
      return null;
    }
  }
  return null;
}

function getState() {
  return loadState() || {
    categories: clone(MOCK_CATEGORIES),
    documents: clone(MOCK_DOCUMENTS),
    versions: clone(MOCK_VERSIONS),
  };
}

function saveState(state) {
  localStorage.setItem(STATE_KEY, JSON.stringify(state));
}

function getUser() {
  const saved = localStorage.getItem(USER_KEY);
  if (saved) {
    try {
      return JSON.parse(saved);
    } catch (_) {
      return null;
    }
  }
  return null;
}

function setUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function categoryName(state, categoryId) {
  const category = state.categories.find((item) => item.id === Number(categoryId));
  return category ? category.name : "未分类";
}

function getDocument(state, id) {
  return state.documents.find((item) => item.id === Number(id));
}

function getVersions(state, documentId) {
  return state.versions[documentId] || [];
}

function currentVersion(state, documentId) {
  const versions = getVersions(state, documentId);
  return versions.length ? versions[0] : null;
}

function formatTime(value) {
  return value || "-";
}

function renderTopbar() {
  const user = getUser() || DEFAULT_USER;
  document.querySelectorAll("#topbar").forEach((node) => {
    node.innerHTML = `
      <span class="user-pill">${user.name} · ${
        user.role === "admin" ? "管理员" : "教师"
      }</span>
      <a class="btn btn-outline" href="index.html">退出</a>
    `;
  });
}

function initLogin() {
  document.getElementById("loginForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const username = document.getElementById("username").value.trim();
    const name = document.getElementById("name").value.trim();
    const password = document.getElementById("password").value;
    const role = document.getElementById("role").value;
    if (!username || !name || !password) {
      alert("请填写工号、姓名和初始密码");
      return;
    }
    setUser({ username, name, role });
    window.location.href = "categories.html";
  });
}

function initCategories() {
  renderTopbar();
  const state = getState();
  const container = document.getElementById("categoryList");
  container.innerHTML = state.categories
    .map((category) => {
      const count = state.documents.filter(
        (doc) => doc.categoryId === category.id
      ).length;
      return `
        <a class="card category-card" href="documents.html?category_id=${category.id}">
          <h3>${category.name}</h3>
          <p>${category.description}</p>
          <span class="count">${count} 份文档</span>
        </a>
      `;
    })
    .join("");
}

function initDocuments() {
  renderTopbar();
  const state = getState();
  const categoryId = Number(qs("category_id") || 0);
  const filter = document.getElementById("categoryFilter");
  const list = document.getElementById("documentList");

  filter.innerHTML =
    '<option value="0">全部分类</option>' +
    state.categories
      .map(
        (category) =>
          `<option value="${category.id}" ${
            category.id === categoryId ? "selected" : ""
          }>${category.name}</option>`
      )
      .join("");

  function render() {
    const selected = Number(filter.value || 0);
    const documents = state.documents.filter(
      (doc) => !selected || doc.categoryId === selected
    );
    list.innerHTML = documents.length
      ? documents
          .map((doc) => {
            const current = currentVersion(state, doc.id);
            return `
              <tr>
                <td><a href="document-detail.html?id=${doc.id}">${doc.title}</a></td>
                <td>${categoryName(state, doc.categoryId)}</td>
                <td>${doc.owner.name}</td>
                <td>v${current ? current.versionNumber : 0}</td>
                <td>${formatTime(doc.updatedAt)}</td>
              </tr>
            `;
          })
          .join("")
      : '<tr><td colspan="5" class="muted">该分类暂无文档</td></tr>';
  }

  filter.addEventListener("change", () => {
    const next = new URLSearchParams(window.location.search);
    if (filter.value === "0") {
      next.delete("category_id");
    } else {
      next.set("category_id", filter.value);
    }
    window.location.search = next.toString();
  });

  render();
}

function initDocumentDetail() {
  renderTopbar();
  const state = getState();
  const doc = getDocument(state, qs("id"));
  if (!doc) {
    document.getElementById("detail").innerHTML =
      '<div class="card muted">文档不存在</div>';
    return;
  }
  const current = currentVersion(state, doc.id);
  const isAdmin = (getUser() || DEFAULT_USER).role === "admin";
  const canUpload = isAdmin || (getUser() || DEFAULT_USER).username === doc.owner.username;

  document.getElementById("pageTitle").textContent = doc.title;
  document.getElementById("detail").innerHTML = `
    <div class="card">
      <dl class="detail-list">
        <dt>文档标题</dt><dd>${doc.title}</dd>
        <dt>所属分类</dt><dd>${categoryName(state, doc.categoryId)}</dd>
        <dt>负责人</dt><dd>${doc.owner.name}</dd>
        <dt>当前版本</dt><dd>v${current ? current.versionNumber : 0}</dd>
        <dt>最近更新</dt><dd>${formatTime(doc.updatedAt)}</dd>
      </dl>
      <div class="actions">
        <a class="btn btn-primary" href="download.html?id=${doc.id}&version_id=${
          current ? current.id : ""
        }">下载当前版本</a>
        ${
          canUpload
            ? `<a class="btn btn-outline" href="upload-version.html?id=${doc.id}">上传新版本</a>`
            : '<span class="notice" style="margin:0">你当前为只读权限，不能上传新版本</span>'
        }
        <a class="btn btn-outline" href="versions.html?id=${doc.id}">查看历史版本</a>
      </div>
    </div>
  `;
}

function initUpload() {
  renderTopbar();
  const state = getState();
  const doc = getDocument(state, qs("id"));
  if (!doc) {
    document.getElementById("upload").innerHTML =
      '<div class="card muted">文档不存在</div>';
    return;
  }
  document.getElementById("docTitle").textContent = doc.title;
  document.getElementById("backLink").href = `document-detail.html?id=${doc.id}`;
  document.getElementById("uploadForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const filename = document.getElementById("file").value.split("\\").pop();
    const changelog = document.getElementById("changelog").value.trim();
    if (!filename) {
      alert("请选择文件");
      return;
    }

    const versions = getVersions(state, doc.id);
    const nextNumber = versions.length ? versions[0].versionNumber + 1 : 1;
    const user = getUser() || DEFAULT_USER;
    const now = new Date();
    const createdAt = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(
      2,
      "0"
    )}-${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(
      2,
      "0"
    )}:${String(now.getMinutes()).padStart(2, "0")}`;

    const newVersion = {
      id: Date.now(),
      versionNumber: nextNumber,
      filename,
      changelog: changelog || "未填写变更说明",
      uploader: user.name,
      createdAt,
    };
    state.versions[doc.id] = [newVersion, ...versions];
    doc.updatedAt = createdAt;
    saveState(state);
    window.location.href = `document-detail.html?id=${doc.id}`;
  });
}

function initVersions() {
  renderTopbar();
  const state = getState();
  const doc = getDocument(state, qs("id"));
  if (!doc) {
    document.getElementById("versions").innerHTML =
      '<div class="card muted">文档不存在</div>';
    return;
  }
  document.getElementById("docTitle").textContent = doc.title;
  const versions = getVersions(state, doc.id);
  document.getElementById("versions").innerHTML = versions.length
    ? versions
        .map(
          (version) => `
            <div class="card">
              <div class="toolbar">
                <strong>v${version.versionNumber}</strong>
                <a class="btn btn-outline" href="download.html?id=${doc.id}&version_id=${version.id}">下载</a>
              </div>
              <dl class="detail-list">
                <dt>文件名</dt><dd>${version.filename}</dd>
                <dt>变更说明</dt><dd>${version.changelog}</dd>
                <dt>上传人</dt><dd>${version.uploader}</dd>
                <dt>上传时间</dt><dd>${version.createdAt}</dd>
              </dl>
            </div>
          `
        )
        .join("")
    : '<div class="card muted">暂无历史版本</div>';
}

function initDownload() {
  renderTopbar();
  const state = getState();
  const doc = getDocument(state, qs("id"));
  const version = getVersions(state, qs("id")).find(
    (item) => item.id === Number(qs("version_id"))
  );
  if (!doc || !version) {
    document.getElementById("download").innerHTML =
      '<div class="card muted">文件不存在</div>';
    return;
  }
  document.getElementById("download").innerHTML = `
    <div class="card">
      <dl class="detail-list">
        <dt>文档标题</dt><dd>${doc.title}</dd>
        <dt>文件名</dt><dd>${version.filename}</dd>
        <dt>版本号</dt><dd>v${version.versionNumber}</dd>
        <dt>上传人</dt><dd>${version.uploader}</dd>
      </dl>
      <div class="actions">
        <button class="btn btn-primary" id="confirmDownload">确认下载</button>
        <a class="btn btn-outline" href="document-detail.html?id=${doc.id}">返回详情</a>
      </div>
    </div>
  `;
  document.getElementById("confirmDownload").addEventListener("click", () => {
    alert(`正在下载：${version.filename}`);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "login") initLogin();
  if (page === "categories") initCategories();
  if (page === "documents") initDocuments();
  if (page === "detail") initDocumentDetail();
  if (page === "upload") initUpload();
  if (page === "versions") initVersions();
  if (page === "download") initDownload();
});
