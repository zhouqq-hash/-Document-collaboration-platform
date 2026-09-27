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


const STATUS_LABELS = {
  active: "正常",
  archived: "归档",
  deprecated: "废弃",
};

function statusBadge(status) {
  const label = STATUS_LABELS[status] || status;
  return `<span class="status-badge status-${status}">${escapeHtml(label)}</span>`;
}


function createSearchableSelect({
  options = [],
  value = "",
  placeholder = "请选择",
  emptyText = "无匹配选项",
  onchange,
} = {}) {
  const root = document.createElement("div");
  root.className = "search-select";

  const selected =
    options.find((item) => String(item.value) === String(value)) || null;

  root.innerHTML = `
    <button type="button" class="search-select-trigger" aria-haspopup="listbox" aria-expanded="false">
      <span class="search-select-value"></span>
      <span class="search-select-caret" aria-hidden="true">▾</span>
    </button>
    <div class="search-select-menu" hidden>
      <input type="text" class="search-select-input" placeholder="搜索..." />
      <ul class="search-select-list" role="listbox"></ul>
    </div>
  `;

  const trigger = root.querySelector(".search-select-trigger");
  const valueEl = root.querySelector(".search-select-value");
  const menu = root.querySelector(".search-select-menu");
  const input = root.querySelector(".search-select-input");
  const listEl = root.querySelector(".search-select-list");

  let currentValue = value;
  let visibleOptions = [];
  let highlightedIndex = -1;

  function labelFor(itemValue) {
    const found = options.find(
      (item) => String(item.value) === String(itemValue)
    );
    return found ? found.label : "";
  }

  function renderValue() {
    const label = labelFor(currentValue);
    valueEl.textContent = label || placeholder;
    valueEl.classList.toggle("placeholder", !label);
    trigger.setAttribute("aria-expanded", menu.hidden ? "false" : "true");
  }

  function updateHighlight() {
    listEl.querySelectorAll(".search-select-option").forEach((node, index) => {
      node.classList.toggle("highlighted", index === highlightedIndex);
    });
  }

  function renderOptions() {
    const query = input.value.trim().toLowerCase();
    visibleOptions = query
      ? options.filter((item) =>
          String(item.label).toLowerCase().includes(query)
        )
      : options;
    highlightedIndex = visibleOptions.length ? 0 : -1;

    if (visibleOptions.length) {
      listEl.innerHTML = visibleOptions
        .map((item, index) => {
          const isSelected = String(item.value) === String(currentValue);
          return `<li class="search-select-option${
            isSelected ? " selected" : ""
          }" role="option" data-index="${index}" aria-selected="${isSelected}">
            ${escapeHtml(item.label)}
          </li>`;
        })
        .join("");
    } else {
      listEl.innerHTML = `<li class="search-select-empty">${escapeHtml(
        emptyText
      )}</li>`;
    }
    updateHighlight();
  }

  function open() {
    menu.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    input.value = "";
    renderOptions();
    input.focus();
  }

  function close() {
    menu.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
  }

  function choose(item) {
    currentValue = item.value;
    renderValue();
    close();
    if (onchange) {
      onchange(currentValue);
    }
  }

  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    if (menu.hidden) {
      open();
    } else {
      close();
    }
  });

  input.addEventListener("input", renderOptions);
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (visibleOptions.length) {
        highlightedIndex = (highlightedIndex + 1) % visibleOptions.length;
        updateHighlight();
      }
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (visibleOptions.length) {
        highlightedIndex =
          (highlightedIndex - 1 + visibleOptions.length) %
          visibleOptions.length;
        updateHighlight();
      }
    } else if (event.key === "Enter") {
      event.preventDefault();
      const option = visibleOptions[highlightedIndex];
      if (option) {
        choose(option);
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      close();
    }
  });

  listEl.addEventListener("click", (event) => {
    const node = event.target.closest(".search-select-option");
    if (!node) {
      return;
    }
    const option = visibleOptions[Number(node.dataset.index)];
    if (option) {
      choose(option);
    }
  });

  document.addEventListener("click", (event) => {
    if (!root.contains(event.target)) {
      close();
    }
  });

  renderValue();

  return {
    root,
    getValue: () => currentValue,
    setValue: (nextValue) => {
      currentValue = nextValue;
      renderValue();
    },
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
  const adminNav =
    user.role === "admin"
      ? `
        <nav class="admin-nav">
          <a href="create-document.html">新建文档</a>
          <a href="manage-categories.html">分类管理</a>
        </nav>
      `
      : "";
  const avatar = user.avatar_url
    ? `<img class="avatar" src="${escapeHtml(user.avatar_url)}" alt="微信头像" />`
    : "";
  const wechatTag = user.wechat_bound
    ? '<span class="tag-wechat">微信</span>'
    : "";
  document.querySelectorAll("#topbar").forEach((node) => {
    node.innerHTML = `
      ${adminNav}
      <nav class="admin-nav"><a href="account.html">账号设置</a></nav>
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

const WECHAT_POLL_INTERVAL = 2000;
const WECHAT_POLL_LIMIT = 60;

let wechatConfig = null;
let wechatPollTimer = null;

async function loadWechatConfig() {
  if (wechatConfig) {
    return wechatConfig;
  }
  try {
    wechatConfig = await apiRequest(
      "/api/auth/wechat/config",
      {},
      { redirectOn401: false }
    );
  } catch (_) {
    wechatConfig = { mode: "disabled", hint: "微信登录配置读取失败" };
  }
  return wechatConfig;
}

function stopWechatPolling() {
  if (wechatPollTimer) {
    window.clearInterval(wechatPollTimer);
    wechatPollTimer = null;
  }
}

// 扫码是在新窗口里完成的，主页面只能轮询当前登录状态来判断结果
function startWechatPolling({ check, onSuccess, onTimeout }) {
  stopWechatPolling();
  let attempts = 0;
  wechatPollTimer = window.setInterval(async () => {
    attempts += 1;
    if (attempts > WECHAT_POLL_LIMIT) {
      stopWechatPolling();
      if (onTimeout) {
        onTimeout();
      }
      return;
    }
    try {
      const user = await apiRequest("/api/auth/me", {}, { redirectOn401: false });
      if (!check(user)) {
        return;
      }
      stopWechatPolling();
      currentUser = user;
      onSuccess(user);
    } catch (_) {
      // 还没扫码完成，等下一轮
    }
  }, WECHAT_POLL_INTERVAL);
}

// 微信内置浏览器：公众号网页授权必须整页跳转，不能指望弹窗
function isWechatBrowser() {
  return /micromessenger/i.test(navigator.userAgent || "");
}

async function openWechatAuthorize({ bind = false } = {}) {
  let info = null;
  try {
    info = await apiRequest(
      `/api/auth/wechat/authorize-url${bind ? "?bind=1" : ""}`
    );
  } catch (error) {
    alert(error.message || "微信登录暂不可用");
    return null;
  }
  if (!info || !info.authorize_url) {
    alert("微信登录暂不可用");
    return null;
  }

  if (isWechatBrowser()) {
    // 在微信里直接跳走，回来后由 wechat-callback.html 接着收尾
    window.location.href = info.authorize_url;
    return null;
  }

  const popup = window.open(
    info.authorize_url,
    "wechatAuthorize",
    "width=520,height=640,menubar=no,toolbar=no"
  );
  if (!popup) {
    // 弹窗被拦截时退回当前窗口跳转，回调页会自己接着走
    window.location.href = info.authorize_url;
    return null;
  }
  return info;
}

function showLoginNotice(message, isError = true) {
  const container = document.getElementById("loginNotice");
  if (!container) {
    alert(message);
    return;
  }
  container.innerHTML = `
    <div class="notice ${isError ? "" : "notice-ok"}">${escapeHtml(message)}</div>
  `;
}

async function initWechatLogin() {
  const container = document.getElementById("wechatLogin");
  if (!container) {
    return;
  }

  const config = await loadWechatConfig();
  container.hidden = false;

  if (config.mode === "disabled") {
    container.innerHTML =
      '<p class="muted">微信登录未开启（未配置 WECHAT_APP_ID / WECHAT_APP_SECRET）</p>';
    return;
  }

  if (config.mode === "mock") {
    container.innerHTML = `
      <button class="btn btn-wechat" id="wechatMockButton" type="button">模拟微信扫码登录</button>
      <p class="muted wechat-hint">${escapeHtml(config.hint)}</p>
      <details class="wechat-advanced">
        <summary>模拟参数（演示不同微信用户时使用）</summary>
        <div class="form-grid">
          <div>
            <label for="wechatOpenid">OpenID</label>
            <input id="wechatOpenid" value="${escapeHtml(config.mock.openid)}" />
          </div>
          <div>
            <label for="wechatNickname">微信昵称</label>
            <input id="wechatNickname" value="${escapeHtml(config.mock.nickname)}" />
          </div>
        </div>
      </details>
    `;

    const button = document.getElementById("wechatMockButton");
    button.addEventListener("click", async () => {
      const openid = document.getElementById("wechatOpenid").value.trim();
      const nickname = document.getElementById("wechatNickname").value.trim();
      button.disabled = true;
      button.textContent = "登录中...";
      try {
        await apiRequest(
          "/api/auth/wechat/mock-login",
          { method: "POST", body: JSON.stringify({ openid, nickname }) },
          { redirectOn401: false }
        );
        window.location.href = "categories.html";
      } catch (error) {
        showLoginNotice(error.message);
        button.disabled = false;
        button.textContent = "模拟微信扫码登录";
      }
    });
    return;
  }

  const mpMode = config.authorize_mode === "mp";
  const inWechat = isWechatBrowser();
  const buttonText = mpMode ? "微信登录" : "微信扫码登录";
  let hint = "点击后弹出微信二维码，扫码成功后自动进入系统";
  if (mpMode && inWechat) {
    hint = "点下面的按钮会跳到微信授权页，确认后自动回到系统";
  } else if (mpMode) {
    hint =
      "当前是公众号网页授权（测试号常用）：请把本页网址发到微信里打开，或改成扫码模式（WECHAT_AUTHORIZE_MODE=open）";
  }

  container.innerHTML = `
    <button class="btn btn-wechat" id="wechatLiveButton" type="button">${escapeHtml(
      buttonText
    )}</button>
    <p class="muted wechat-hint">${escapeHtml(hint)}</p>
  `;

  document
    .getElementById("wechatLiveButton")
    .addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      const info = await openWechatAuthorize();
      if (!info) {
        button.disabled = false;
        return;
      }
      showLoginNotice(
        mpMode
          ? "已跳转微信授权页，请在微信中确认"
          : "已打开微信二维码，请在弹窗中扫码",
        false
      );
      startWechatPolling({
        check: () => true,
        onSuccess: () => {
          window.location.href = "categories.html";
        },
        onTimeout: () => {
          button.disabled = false;
          showLoginNotice("没有等到微信授权结果，请重试");
        },
      });
    });
}

async function initLogin() {
  const params = new URLSearchParams(window.location.search);
  const hasNotice = params.has("message") || params.get("wechat") === "error";

  if (!hasNotice) {
    // 已经有会话时直接进系统，别让人重复登录
    try {
      await getCurrentUser();
      window.location.href = "categories.html";
      return;
    } catch (_) {
      // 未登录，继续走登录流程
    }
  }

  if (params.get("wechat") === "error" || params.has("message")) {
    showLoginNotice(params.get("message") || "微信登录失败");
  }

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
      showLoginNotice(error.message);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "登录";
    }
  });

  await initWechatLogin();
}

// 微信回调页：把结果通过 postMessage 告诉打开它的主页面，然后自己收尾
function initWechatCallback() {
  const params = new URLSearchParams(window.location.search);
  const failed = params.get("wechat") === "error";
  const message = params.get("message") || "";
  const errorCode = params.get("error") || "";
  const isPopup = Boolean(window.opener && !window.opener.closed);
  const container = document.getElementById("wechatResult");

  if (container) {
    container.innerHTML = failed
      ? `
        <div class="notice">${escapeHtml(message || "微信登录失败，请重试")}</div>
        ${
          errorCode
            ? `<p class="muted">错误码：${escapeHtml(errorCode)}</p>`
            : ""
        }
        <p class="actions">
          <button class="btn btn-outline" id="copyWechatError" type="button">复制错误信息</button>
          <a class="btn btn-outline" href="index.html">返回登录</a>
        </p>
        <p class="muted">
          后端终端里搜 <code>wechat:</code> 能看到这次登录每一步发生了什么，
          也可以执行 <code>flask --app backend\\run.py wechat-log</code> 回看。
        </p>
      `
      : '<p class="muted">微信登录成功，正在返回…</p>';
  }

  const copyButton = document.getElementById("copyWechatError");
  if (copyButton) {
    copyButton.addEventListener("click", async () => {
      const text = `微信登录失败：${message || "未知原因"}${
        errorCode ? `（${errorCode}）` : ""
      }`;
      try {
        await navigator.clipboard.writeText(text);
        copyButton.textContent = "已复制";
      } catch (_) {
        window.prompt("手动复制下面的错误信息：", text);
      }
    });
  }

  if (isPopup) {
    try {
      window.opener.postMessage(
        {
          type: "wechat-login",
          status: failed ? "error" : "success",
          message,
        },
        window.location.origin
      );
    } catch (_) {
      // 跨窗口通信失败也不影响后面的兜底
    }
    window.setTimeout(() => window.close(), failed ? 1500 : 400);
    return;
  }

  if (!failed) {
    window.location.replace("categories.html");
  }
}

function loginMethodText(user) {
  if (user.wechat_bound && user.password_login) {
    return "微信 + 工号密码";
  }
  if (user.wechat_bound) {
    return "仅微信";
  }
  return "工号密码";
}

function renderAccountInfo(user) {
  const container = document.getElementById("accountInfo");
  if (!container) {
    return;
  }
  container.innerHTML = `
    <dl class="detail-list">
      <dt>工号</dt><dd>${escapeHtml(user.username)}</dd>
      <dt>姓名</dt><dd>${escapeHtml(user.name)}</dd>
      <dt>角色</dt><dd>${user.role === "admin" ? "管理员" : "教师"}</dd>
      <dt>登录方式</dt><dd>${escapeHtml(loginMethodText(user))}</dd>
      <dt>微信绑定</dt><dd>${user.wechat_bound ? "已绑定" : "未绑定"}</dd>
    </dl>
  `;
}

async function refreshAccount() {
  currentUser = null;
  const fresh = await getCurrentUser();
  renderTopbar(fresh);
  renderAccountInfo(fresh);
  await renderWechatBinding(fresh);
  return fresh;
}

async function renderWechatBinding(user) {
  const container = document.getElementById("wechatBinding");
  if (!container) {
    return;
  }
  const config = await loadWechatConfig();

  if (user.wechat_bound) {
    container.innerHTML = `
      <p>当前账号已绑定微信。</p>
      ${
        user.password_login
          ? '<button class="btn btn-outline" id="wechatUnbindButton" type="button">解绑微信</button>'
          : '<p class="muted">该账号由微信创建，解绑后将无法登录，因此不提供解绑。</p>'
      }
    `;
    const unbindButton = document.getElementById("wechatUnbindButton");
    if (unbindButton) {
      unbindButton.addEventListener("click", async () => {
        if (!window.confirm("确定解绑微信吗？解绑后需要用工号密码登录。")) {
          return;
        }
        try {
          await apiRequest("/api/auth/wechat/unbind", { method: "POST" });
          await refreshAccount();
          showPageMessage("accountNotice", "已解绑微信", false);
        } catch (error) {
          showPageMessage("accountNotice", error.message, true);
        }
      });
    }
    return;
  }

  if (config.mode === "disabled") {
    container.innerHTML =
      '<p class="muted">微信登录未开启，暂不支持绑定。</p>';
    return;
  }

  container.innerHTML = `
    <p class="muted">绑定微信后，可以直接用微信扫码登录这个账号，权限和现在一致。</p>
    <button class="btn btn-wechat" id="wechatBindButton" type="button">绑定微信</button>
  `;

  document
    .getElementById("wechatBindButton")
    .addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        if (config.mode === "mock") {
          await apiRequest("/api/auth/wechat/bind", {
            method: "POST",
            body: JSON.stringify({
              openid: config.mock.openid,
              nickname: config.mock.nickname,
            }),
          });
          await refreshAccount();
          showPageMessage(
            "accountNotice",
            `已绑定演示微信（${config.mock.openid}）`,
            false
          );
          return;
        }

        const info = await openWechatAuthorize({ bind: true });
        if (!info) {
          button.disabled = false;
          return;
        }
        showPageMessage(
          "accountNotice",
          "已打开微信二维码，请在弹窗中扫码完成绑定",
          false
        );
        startWechatPolling({
          check: (candidate) => candidate.wechat_bound,
          onSuccess: async () => {
            await refreshAccount();
            showPageMessage("accountNotice", "微信绑定成功", false);
          },
          onTimeout: () => {
            button.disabled = false;
            showPageMessage("accountNotice", "没有等到绑定结果，请重试", true);
          },
        });
      } catch (error) {
        button.disabled = false;
        showPageMessage("accountNotice", error.message, true);
      }
    });
}

async function initAccount() {
  const user = await requireUser();
  renderAccountInfo(user);
  await renderWechatBinding(user);

  window.addEventListener("message", async (event) => {
    if (event.origin !== window.location.origin) {
      return;
    }
    const data = event.data || {};
    if (data.type !== "wechat-login") {
      return;
    }
    if (data.status === "success") {
      await refreshAccount();
      showPageMessage("accountNotice", "微信绑定成功", false);
    } else {
      showPageMessage("accountNotice", data.message || "微信绑定失败", true);
    }
  });
}

window.addEventListener("message", (event) => {
  if (event.origin !== window.location.origin) {
    return;
  }
  const data = event.data || {};
  if (data.type !== "wechat-login" || document.body.dataset.page !== "login") {
    return;
  }
  if (data.status === "success") {
    window.location.href = "categories.html";
  } else {
    showLoginNotice(data.message || "微信登录失败");
  }
});

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
  const filterWrap = document.getElementById("categoryFilterWrap");
  const list = document.getElementById("documentList");

  try {
    const categories = await apiRequest("/api/categories");
    const filter = createSearchableSelect({
      options: [
        { value: "", label: "全部分类" },
        ...categories.map((category) => ({
          value: String(category.id),
          label: category.name,
        })),
      ],
      value: categoryId,
      placeholder: "全部分类",
      onchange: (value) => {
        const next = new URLSearchParams(window.location.search);
        if (value) {
          next.set("category_id", value);
        } else {
          next.delete("category_id");
        }
        window.location.search = next.toString();
      },
    });
    filterWrap.replaceChildren(filter.root);

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
                <td>${statusBadge(document.status)}</td>
                <td>v${current ? current.version_number : 0}</td>
                <td>${formatTime(document.updated_at)}</td>
              </tr>
            `;
          })
          .join("")
      : '<tr><td colspan="6" class="muted">该分类暂无文档</td></tr>';
  } catch (error) {
    list.innerHTML = `<tr><td colspan="6" class="notice">${escapeHtml(
      error.message
    )}</td></tr>`;
  }
}

async function initDocumentDetail() {
  const user = await requireUser();
  const documentId = qs("id");
  const container = document.getElementById("detail");

  try {
    // 注意：不要把这个变量命名为 document，否则会遮蔽浏览器的全局 document
    const doc = await apiRequest(`/api/documents/${documentId}`);
    const current = doc.current_version;
    const canUpload =
      user.role === "admin" || user.id === doc.owner.id;

    document.getElementById("pageTitle").textContent = doc.title;
    container.innerHTML = `
      <div class="card">
        <dl class="detail-list">
          <dt>文档标题</dt><dd>${escapeHtml(doc.title)}</dd>
          <dt>所属分类</dt><dd>${escapeHtml(doc.category.name)}</dd>
          <dt>负责人</dt><dd>${escapeHtml(doc.owner.name)}</dd>
          <dt>状态</dt><dd>${statusBadge(doc.status)}</dd>
          <dt>当前版本</dt><dd>v${current ? current.version_number : 0}</dd>
          <dt>最近更新</dt><dd>${formatTime(doc.updated_at)}</dd>
          <dt>说明</dt><dd>${escapeHtml(doc.description || "-")}</dd>
        </dl>
        <div class="actions">
          ${
            current
              ? `<a class="btn btn-primary" href="download.html?id=${doc.id}&version_id=${current.id}">下载当前版本</a>`
              : ""
          }
          ${
            canUpload
              ? `<a class="btn btn-outline" href="upload-version.html?id=${doc.id}">上传新版本</a>`
              : '<span class="notice" style="margin:0">你当前为只读权限，不能上传新版本</span>'
          }
          ${
            user.role === "admin"
              ? `<a class="btn btn-outline" href="edit-document.html?id=${doc.id}">编辑文档</a>`
              : ""
          }
          <a class="btn btn-outline" href="versions.html?id=${doc.id}">查看历史版本</a>
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
    const doc = await apiRequest(`/api/documents/${documentId}`);
    document.getElementById("docTitle").textContent = doc.title;
    backLink.href = `document-detail.html?id=${doc.id}`;
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
    const doc = await apiRequest(`/api/documents/${documentId}`);
    const versions = await apiRequest(
      `/api/documents/${documentId}/versions`
    );
    document.getElementById("docTitle").textContent = doc.title;
    container.innerHTML = versions.length
      ? versions
          .map(
            (version) => `
              <div class="card">
                <div class="toolbar">
                  <strong>v${version.version_number}</strong>
                  <a class="btn btn-outline" href="download.html?id=${doc.id}&version_id=${version.id}">下载</a>
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
    const doc = await apiRequest(`/api/documents/${documentId}`);
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
          <dt>文档标题</dt><dd>${escapeHtml(doc.title)}</dd>
          <dt>文件名</dt><dd>${escapeHtml(version.filename)}</dd>
          <dt>版本号</dt><dd>v${version.version_number}</dd>
          <dt>上传人</dt><dd>${escapeHtml(version.uploader.name)}</dd>
        </dl>
        <div class="actions">
          <button class="btn btn-primary" id="confirmDownload" type="button">确认下载</button>
          <a class="btn btn-outline" href="document-detail.html?id=${doc.id}">返回详情</a>
        </div>
      </div>
    `;
    document.getElementById("confirmDownload").addEventListener("click", () => {
      window.location.href = `/api/documents/${doc.id}/versions/${version.id}/download`;
    });
  } catch (error) {
    showPageMessage("download", error.message, true);
  }
}


async function initCreateDocument() {
  const user = await requireUser();
  const form = document.getElementById("createDocumentForm");

  if (user.role !== "admin") {
    form.closest(".card").style.display = "none";
    showPageMessage("pageMessage", "只有管理员可以新建文档。", true);
    return;
  }

  let categorySelect;
  let ownerSelect;

  try {
    const [categories, users] = await Promise.all([
      apiRequest("/api/categories"),
      apiRequest("/api/users"),
    ]);

    categorySelect = createSearchableSelect({
      options: categories.map((category) => ({
        value: String(category.id),
        label: category.name,
      })),
      placeholder: "请选择分类",
    });
    document.getElementById("categorySelect").appendChild(categorySelect.root);

    ownerSelect = createSearchableSelect({
      options: users.map((item) => ({
        value: String(item.id),
        label: `${item.name}（${item.username}）`,
      })),
      placeholder: "请选择负责人",
    });
    document.getElementById("ownerSelect").appendChild(ownerSelect.root);
  } catch (error) {
    showPageMessage("pageMessage", error.message, true);
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = document.getElementById("title").value.trim();
    const file = document.getElementById("file").files[0];
    const categoryId = categorySelect.getValue();
    const ownerId = ownerSelect.getValue();

    if (!title) {
      alert("请填写文档标题");
      return;
    }
    if (!categoryId) {
      alert("请选择分类");
      return;
    }
    if (!ownerId) {
      alert("请选择负责人");
      return;
    }
    if (!file) {
      alert("请选择文件");
      return;
    }

    const formData = new FormData();
    formData.append("title", title);
    formData.append("category_id", categoryId);
    formData.append("owner_id", ownerId);
    formData.append("description", document.getElementById("description").value.trim());
    formData.append("changelog", document.getElementById("changelog").value.trim());
    formData.append("file", file);

    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = "创建中...";
    try {
      const doc = await apiRequest("/api/documents", {
        method: "POST",
        body: formData,
      });
      window.location.href = `document-detail.html?id=${doc.id}`;
    } catch (error) {
      alert(error.message);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "创建文档";
    }
  });
}


async function initManageCategories() {
  const user = await requireUser();
  const form = document.getElementById("createCategoryForm");
  const createCard = document.getElementById("createCategoryCard");
  const listCard = document.getElementById("categoryManageCard");
  const formTitle = document.getElementById("categoryFormTitle");
  const submitButton = document.getElementById("categorySubmitButton");
  const cancelButton = document.getElementById("categoryCancelButton");
  const nameInput = document.getElementById("categoryName");
  const sortInput = document.getElementById("sortOrder");

  if (user.role !== "admin") {
    createCard.style.display = "none";
    listCard.style.display = "none";
    showPageMessage("pageMessage", "只有管理员可以管理分类。", true);
    return;
  }

  let editingId = null;
  let currentCategories = [];

  function resetForm() {
    editingId = null;
    formTitle.textContent = "新建分类";
    submitButton.textContent = "新建分类";
    cancelButton.hidden = true;
    nameInput.value = "";
    sortInput.value = "0";
  }

  function renderActions(category) {
    return `
      <button class="btn btn-outline" data-action="edit" data-id="${category.id}" type="button">编辑</button>
      <button class="btn btn-danger" data-action="delete" data-id="${category.id}" type="button">删除</button>
    `;
  }

  function bindRowActions() {
    const container = document.getElementById("categoryManageList");
    container.querySelectorAll('[data-action="edit"]').forEach((button) => {
      button.addEventListener("click", () => {
        const category = currentCategories.find(
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
        createCard.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });

    container.querySelectorAll('[data-action="delete"]').forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.id;
        if (!window.confirm("确定删除该分类吗？删除后不可恢复。")) {
          return;
        }
        try {
          await apiRequest(`/api/categories/${id}`, { method: "DELETE" });
          resetForm();
          await reload();
        } catch (error) {
          alert(error.message);
        }
      });
    });
  }

  async function reload() {
    const container = document.getElementById("categoryManageList");
    try {
      currentCategories = await apiRequest("/api/categories");
      container.innerHTML = currentCategories.length
        ? `
          <table class="table">
            <thead>
              <tr>
                <th>名称</th>
                <th>排序</th>
                <th>文档数</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              ${currentCategories
                .map(
                  (category) => `
                    <tr>
                      <td>${escapeHtml(category.name)}</td>
                      <td>${escapeHtml(category.sort_order)}</td>
                      <td>${category.document_count}</td>
                      <td>${formatTime(category.created_at)}</td>
                      <td class="actions">${renderActions(category)}</td>
                    </tr>
                  `
                )
                .join("")}
            </tbody>
          </table>
        `
        : '<div class="card muted">暂无分类</div>';
      bindRowActions();
    } catch (error) {
      showPageMessage("pageMessage", error.message, true);
    }
  }

  await reload();

  cancelButton.addEventListener("click", resetForm);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = nameInput.value.trim();
    const sortOrder = sortInput.value;

    if (!name) {
      alert("请填写分类名称");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = editingId ? "保存中..." : "创建中...";
    try {
      const body = JSON.stringify({ name, sort_order: Number(sortOrder) || 0 });
      if (editingId) {
        await apiRequest(`/api/categories/${editingId}`, {
          method: "PATCH",
          body,
        });
      } else {
        await apiRequest("/api/categories", { method: "POST", body });
      }
      resetForm();
      await reload();
    } catch (error) {
      alert(error.message);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = editingId ? "保存修改" : "新建分类";
    }
  });
}


async function initEditDocument() {
  const user = await requireUser();
  const documentId = qs("id");
  const form = document.getElementById("editDocumentForm");

  if (user.role !== "admin") {
    form.closest(".card").style.display = "none";
    showPageMessage("pageMessage", "只有管理员可以编辑文档。", true);
    return;
  }

  let categorySelect;
  let ownerSelect;
  let statusSelect;

  try {
    const [doc, categories, users] = await Promise.all([
      apiRequest(`/api/documents/${documentId}`),
      apiRequest("/api/categories"),
      apiRequest("/api/users"),
    ]);

    document.getElementById("title").value = doc.title;
    document.getElementById("description").value = doc.description || "";
    document.getElementById("docTitle").textContent = doc.title;
    document.getElementById("backLink").href = `document-detail.html?id=${doc.id}`;

    categorySelect = createSearchableSelect({
      options: categories.map((category) => ({
        value: String(category.id),
        label: category.name,
      })),
      value: String(doc.category.id),
      placeholder: "请选择分类",
    });
    document.getElementById("categorySelect").appendChild(categorySelect.root);

    ownerSelect = createSearchableSelect({
      options: users.map((item) => ({
        value: String(item.id),
        label: `${item.name}（${item.username}）`,
      })),
      value: String(doc.owner.id),
      placeholder: "请选择负责人",
    });
    document.getElementById("ownerSelect").appendChild(ownerSelect.root);

    statusSelect = createSearchableSelect({
      options: [
        { value: "active", label: "正常" },
        { value: "archived", label: "归档" },
        { value: "deprecated", label: "废弃" },
      ],
      value: doc.status || "active",
      placeholder: "请选择状态",
    });
    document.getElementById("statusSelect").appendChild(statusSelect.root);
  } catch (error) {
    showPageMessage("pageMessage", error.message, true);
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = document.getElementById("title").value.trim();

    if (!title) {
      alert("请填写文档标题");
      return;
    }

    const payload = {
      title,
      category_id: categorySelect.getValue(),
      owner_id: ownerSelect.getValue(),
      status: statusSelect.getValue(),
      description: document.getElementById("description").value.trim(),
    };

    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = "保存中...";
    try {
      await apiRequest(`/api/documents/${documentId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      window.location.href = `document-detail.html?id=${documentId}`;
    } catch (error) {
      alert(error.message);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "保存修改";
    }
  });
}


document.addEventListener("DOMContentLoaded", async () => {
  const page = document.body.dataset.page;
  try {
    if (page === "login") {
      await initLogin();
    }
    if (page === "wechatCallback") {
      initWechatCallback();
    }
    if (page === "account") {
      await initAccount();
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
    if (page === "createDocument") {
      await initCreateDocument();
    }
    if (page === "manageCategories") {
      await initManageCategories();
    }
    if (page === "editDocument") {
      await initEditDocument();
    }
  } catch (error) {
    if (error.status !== 401) {
      alert(error.message);
    }
  }
});
