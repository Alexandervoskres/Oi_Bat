// Part of СкладAI frontend. Loaded as an ordered classic script (see index.html).
// Shares globals (state, render, helpers) defined in core.js.

const root = document.getElementById("root");

const ROLE_LABELS = {
  admin: "Администратор",
  manager: "Менеджер",
  buyer: "Закупщик",
};

const NAV_ITEMS = [
  { id: "dashboard", label: "Дашборд", adminOnly: false },
  { id: "warehouse", label: "Склад", adminOnly: false },
  { id: "risks", label: "Риски", adminOnly: false },
  { id: "procurement", label: "Закупки", adminOnly: false },
  { id: "orders", label: "Заказы", adminOnly: false },
  { id: "suppliers", label: "Поставщики", adminOnly: false },
  { id: "chat", label: "AI-советник", adminOnly: false },
  { id: "imports", label: "Excel и история", adminOnly: false },
  { id: "reports", label: "Отчеты", adminOnly: false },
  { id: "audit", label: "Аудит", adminOnly: true },
  { id: "users", label: "Пользователи", adminOnly: true },
  { id: "settings", label: "Сервер", adminOnly: false },
];

const MOVEMENT_TYPES = [
  { code: "receipt", label: "Приход" },
  { code: "write_off", label: "Списание" },
  { code: "sale", label: "Продажа" },
  { code: "return", label: "Возврат" },
  { code: "reserve", label: "Резерв" },
  { code: "adjustment", label: "Корректировка" },
];

const MOVEMENT_LABELS = Object.fromEntries(MOVEMENT_TYPES.map((m) => [m.code, m.label]));

const AUDIT_ACTION_LABELS = {
  "product.create": "Создание товара",
  "product.update": "Изменение товара",
  "product.delete": "Удаление товара",
  "product.risk": "Корректировка риска",
  "stock.movement": "Движение склада",
  "user.create": "Создание пользователя",
  "import.upload": "Импорт Excel",
  "report.download": "Скачивание отчёта",
};

const RISK_STATUS_OPTIONS = [
  { code: "", label: "— авто —" },
  { code: "out_of_stock", label: "Нет в наличии" },
  { code: "order_now", label: "Срочно заказать" },
  { code: "discount", label: "Сделать скидку" },
  { code: "dead_stock", label: "Мертвый груз" },
  { code: "growing", label: "Растущий спрос" },
  { code: "ok", label: "Норма" },
];

const PRIORITY_LABELS = {
  critical: "Критический",
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
};

const state = {
  token: localStorage.getItem("skladai_token") || "",
  user: readStoredJson("skladai_user"),
  active: "dashboard",
  dashboard: null,
  error: "",
  warehouse: {
    rows: [],
    search: "",
    status: "",
    loading: false,
    error: "",
  },
  procurement: {
    rows: [],
    quantities: {},
    loading: false,
    error: "",
  },
  risks: {
    rows: [],
    loading: false,
    error: "",
    message: "",
    filter: { status: "", priority: "", mode: "" },
  },
  chat: {
    messages: readSessionJson("skladai_chat_messages") || [],
    loading: false,
    error: "",
    status: null,
    statusLoading: false,
  },
  imports: {
    rows: [],
    file: null,
    message: "",
    loading: false,
    preview: null,
    previewing: false,
  },
  users: {
    rows: [],
    message: "",
    form: {
      username: "",
      full_name: "",
      password: "",
      role: "manager",
    },
  },
  audit: {
    rows: [],
    loading: false,
    error: "",
    filter: { action: "" },
  },
  abc: {
    data: null,
    loaded: false,
    loading: false,
    error: "",
  },
  notifications: {
    items: [],
    unread: 0,
    loading: false,
    error: "",
    open: false,
    onlyUnread: false,
  },
  suppliers: {
    rows: [],
    loading: false,
    error: "",
    message: "",
    editingId: null,
    form: { name: "", contact_person: "", phone: "", email: "", reliability: 3, min_order_amount: 0, payment_terms: "", lead_time_days: 7, notes: "" },
  },
  orders: {
    rows: [],
    loading: false,
    error: "",
    message: "",
    expandedId: null,
  },
  settings: {
    message: "",
    error: "",
  },
  modal: {
    open: false,
    mode: "edit", // "edit" | "create"
    product: null,
    saving: false,
    error: "",
    movements: [],
    movementSaving: false,
    movementError: "",
  },
  riskModal: {
    open: false,
    product: null,
    saving: false,
    error: "",
  },
};

function readStoredJson(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    localStorage.removeItem(key);
    return null;
  }
}

function readSessionJson(key) {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    sessionStorage.removeItem(key);
    return null;
  }
}

function writeSessionJson(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch (_) {
    // Ignore storage errors in private mode.
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatMoney(value) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ru-RU").format(new Date(value));
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatChatTime(value) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function button(label, className = "", attrs = "") {
  return `<button ${attrs} class="button ${className}"><span>${escapeHtml(label)}</span></button>`;
}

// Quote a value for CSV and neutralize spreadsheet formula injection: a cell
// starting with = + - @ (or tab/CR) is prefixed with ' so Excel/Sheets treats
// it as text, not a formula.
function csvCell(value) {
  let s = String(value ?? "");
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return `"${s.replace(/"/g, '""')}"`;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) {
    logout();
    throw new Error("Сессия истекла");
  }
  if (!response.ok) {
    let message = "Ошибка запроса";
    try {
      const data = await response.json();
      message = data.detail || message;
    } catch (_) {
      // Keep default message.
    }
    throw new Error(message);
  }
  return response;
}

function setToken(token, user) {
  state.token = token;
  state.user = user;
  localStorage.setItem("skladai_token", token);
  localStorage.setItem("skladai_user", JSON.stringify(user));
}

function logout() {
  localStorage.removeItem("skladai_token");
  localStorage.removeItem("skladai_user");
  state.token = "";
  state.user = null;
  state.dashboard = null;
  state.active = "dashboard";
  render();
}

function render() {
  if (!state.token || !state.user) {
    root.innerHTML = loginTemplate();
    bindLogin();
    return;
  }

  root.innerHTML = appTemplate();
  bindShell();

  if (state.modal.open) {
    bindModal();
    return;
  }

  if (state.riskModal.open) {
    bindRiskModal();
    return;
  }

  if (!state.dashboard) {
    refreshDashboard();
    return;
  }

  bindActiveScreen();
}

function loginTemplate() {
  return `
    <main class="login-screen">
      <section class="login-panel">
        <div class="brand-mark">AI</div>
        <h1>СкладAI</h1>
        <p>Аналитика склада строительных инструментов с AI-рекомендациями.</p>
        <form id="login-form" class="login-form">
          <label>
            <span>Логин</span>
            <input id="login-username" value="admin" autocomplete="username" />
          </label>
          <label>
            <span>Пароль</span>
            <input id="login-password" type="password" value="admin123" autocomplete="current-password" />
          </label>
          <div id="login-error" class="error-box" hidden></div>
          ${button("Войти", "", 'type="submit" id="login-submit"')}
        </form>
        <div class="login-hint">Тестовый доступ: admin / admin123</div>
      </section>
    </main>
  `;
}

function bindLogin() {
  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = document.getElementById("login-submit");
    const errorBox = document.getElementById("login-error");
    submit.disabled = true;
    submit.querySelector("span").textContent = "Входим...";
    errorBox.hidden = true;

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("login-username").value,
          password: document.getElementById("login-password").value,
        }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Не удалось войти");
      }
      const data = await response.json();
      setToken(data.access_token, data.user);
      await refreshDashboard();
      render();
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.hidden = false;
    } finally {
      submit.disabled = false;
      submit.querySelector("span").textContent = "Войти";
    }
  });
}

function appTemplate() {
  return `
    <div class="app-shell">
      ${sidebarTemplate()}
      <main class="content">
        ${state.error ? `<div class="error-box global-error">${escapeHtml(state.error)}</div>` : ""}
        ${activeTemplate()}
      </main>
      ${state.notifications.open ? notificationsPopoverTemplate() : ""}
      ${state.modal.open ? modalTemplate() : ""}
      ${state.riskModal.open ? riskModalTemplate() : ""}
    </div>
  `;
}

function sidebarTemplate() {
  const items = NAV_ITEMS.filter((item) => !item.adminOnly || state.user.role === "admin");
  return `
    <aside class="sidebar">
      <div class="logo-row">
        <div class="logo">SA</div>
        <div>
          <strong>СкладAI</strong>
          <span>строительный склад</span>
        </div>
        <button class="icon-button notification-trigger" id="notification-trigger" type="button" aria-label="Уведомления">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"></path>
            <path d="M13.7 21a2 2 0 0 1-3.4 0"></path>
          </svg>
          ${state.notifications.unread ? `<span class="nav-badge notification-badge">${state.notifications.unread > 99 ? "99+" : state.notifications.unread}</span>` : ""}
        </button>
      </div>
      <nav>
        ${items
          .map(
            (item) => `
              <button class="nav-item ${state.active === item.id ? "active" : ""}" data-nav="${item.id}">
                <span>${escapeHtml(item.label)}</span>
              </button>
            `,
          )
          .join("")}
      </nav>
      <div class="user-panel">
        <span>${escapeHtml(ROLE_LABELS[state.user.role] || state.user.role)}</span>
        <strong>${escapeHtml(state.user.full_name || state.user.username)}</strong>
        <button id="logout-button" class="logout-button">Выйти</button>
      </div>
    </aside>
  `;
}

function bindShell() {
  document.querySelectorAll("[data-nav]").forEach((buttonEl) => {
    buttonEl.addEventListener("click", async () => {
      state.active = buttonEl.dataset.nav;
      render();
      if (state.active === "warehouse" && !state.warehouse.rows.length) await loadProducts();
      if (state.active === "risks") await loadRisks();
      if (state.active === "procurement") await loadProcurement();
      if (state.active === "orders") await loadOrders();
      if (state.active === "suppliers") await loadSuppliers();
      if (state.active === "imports" && !state.imports.rows.length) await loadImports();
      if (state.active === "audit") await loadAudit();
      if (state.active === "users" && !state.users.rows.length) await loadUsers();
    });
  });
  document.getElementById("notification-trigger")?.addEventListener("click", async () => {
    state.notifications.open = !state.notifications.open;
    render();
    if (state.notifications.open && !state.notifications.items.length) await loadNotifications();
  });
  if (state.notifications.open) bindNotificationsPopover();
  document.getElementById("logout-button").addEventListener("click", logout);
}

function activeTemplate() {
  if (!state.dashboard) {
    return `<div class="screen"><div class="empty-state">Загружаю аналитику...</div></div>`;
  }
  if (state.active === "dashboard") return dashboardTemplate();
  if (state.active === "warehouse") return warehouseTemplate();
  if (state.active === "risks") return risksTemplate();
  if (state.active === "procurement") return procurementTemplate();
  if (state.active === "orders") return ordersTemplate();
  if (state.active === "suppliers") return suppliersTemplate();
  if (state.active === "chat") return chatTemplate();
  if (state.active === "imports") return importsTemplate();
  if (state.active === "reports") return reportsTemplate();
  if (state.active === "audit" && state.user.role === "admin") return auditTemplate();
  if (state.active === "users" && state.user.role === "admin") return usersTemplate();
  return settingsTemplate();
}

function bindActiveScreen() {
  if (state.active === "dashboard") bindDashboard();
  if (state.active === "warehouse") bindWarehouse();
  if (state.active === "risks") bindRisks();
  if (state.active === "procurement") bindProcurement();
  if (state.active === "orders") bindOrders();
  if (state.active === "suppliers") bindSuppliers();
  if (state.active === "chat") bindChat();
  if (state.active === "imports") bindImports();
  if (state.active === "reports") bindReports();
  if (state.active === "audit" && state.user.role === "admin") bindAudit();
  if (state.active === "users" && state.user.role === "admin") bindUsers();
  if (state.active === "settings") bindSettings();
}

async function refreshDashboard() {
  if (!state.token) return;
  try {
    const response = await api("/api/dashboard");
    state.dashboard = await response.json();
    state.error = "";
  } catch (error) {
    state.error = error.message;
  }
  render();
  refreshUnreadBadge();
}

async function refreshUnreadBadge() {
  // Lightweight: keep the notification badge current without opening the popover.
  try {
    const response = await api("/api/notifications?only_unread=true");
    const data = await response.json();
    const next = data.unread || 0;
    if (next !== state.notifications.unread) {
      state.notifications.unread = next;
      render();
    }
  } catch (_) {
    // Non-fatal.
  }
}

function metricTemplate(label, value, hint) {
  return `
    <div class="metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(hint)}</small>
    </div>
  `;
}

function statusPill(status, severity) {
  return `<span class="status-pill status-${escapeHtml(severity || "normal")}">${escapeHtml(status)}</span>`;
}

function deltaBadge(delta, { money = false, invert = false } = {}) {
  const change = delta.change;
  const fmt = (v) => (money ? formatMoney(v) : new Intl.NumberFormat("ru-RU").format(v));
  let dir = change > 0 ? "up" : change < 0 ? "down" : "flat";
  const arrow = change > 0 ? "▲" : change < 0 ? "▼" : "■";
  // For "good when down" metrics (e.g. dead stock) invert the color meaning.
  const tone = dir === "flat" ? "flat" : invert ? (dir === "up" ? "down" : "up") : dir;
  const pct = delta.percent === null || delta.percent === undefined ? "" : ` (${change >= 0 ? "+" : ""}${delta.percent}%)`;
  return `<span class="delta delta-${tone}">${arrow} ${change >= 0 ? "+" : ""}${fmt(change)}${pct}</span>`;
}

function comparisonTemplate(comparison) {
  if (!comparison) return "";
  const cell = (label, delta, opts) => `
    <div class="comparison-cell">
      <span>${escapeHtml(label)}</span>
      <strong>${opts && opts.money ? formatMoney(delta.current) : new Intl.NumberFormat("ru-RU").format(delta.current)}</strong>
      ${deltaBadge(delta, opts)}
    </div>
  `;
  return `
    <section class="panel comparison-panel">
      <div class="panel-title">
        <h3>Динамика по импортам</h3>
        <span>${escapeHtml(comparison.previous_label)} → ${escapeHtml(comparison.current_label)}</span>
      </div>
      <div class="comparison-grid">
        ${cell("Выручка/мес", comparison.revenue, { money: true })}
        ${cell("Продано, шт.", comparison.sold_units, {})}
        ${cell("Остаток, шт.", comparison.stock, {})}
        ${cell("Позиций", comparison.sku_count, {})}
      </div>
    </section>
  `;
}

function dashboardTemplate() {
  const data = state.dashboard;
  const maxSales = Math.max(...(data.top_sales || []).map((item) => item.sold_month), 1);
  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">оперативная панель</span>
          <h2>Дашборд склада</h2>
        </div>
        ${button("Обновить", "", 'type="button" id="refresh-dashboard"')}
      </header>

      <div class="metric-grid">
        ${metricTemplate("Товары", data.metrics.products, "в текущем справочнике")}
        ${metricTemplate("Скоро закончатся", data.metrics.low_stock, "нужна закупка")}
        ${metricTemplate("Мертвый груз", data.metrics.dead_stock, "скидка или ревизия")}
        ${metricTemplate("Продажи/мес", formatMoney(data.metrics.sales_revenue), `${data.metrics.sold_units} шт.`)}
        ${metricTemplate("Склад в закупке", formatMoney(data.metrics.inventory_value), "замороженные деньги")}
      </div>

      <div class="ai-strip">
        <div class="ai-icon">AI</div>
        <div>
          <span>AI-советник</span>
          <p>${escapeHtml(data.ai_summary)}</p>
        </div>
        <button class="button ai-strip-btn" type="button" id="open-chat"><span>Спросить AI</span></button>
      </div>

      ${comparisonTemplate(data.comparison)}

      <div class="dashboard-grid">
        <section class="panel">
          <div class="panel-title">
            <h3>Срочные действия</h3>
            <span>${escapeHtml(data.urgent_actions.length)} поз.</span>
          </div>
          <div class="action-list">
            ${
              data.urgent_actions.length
                ? data.urgent_actions
                    .map(
                      (item) => `
                        <article class="action-row">
                          <div>
                            <strong>${escapeHtml(item.name)}</strong>
                            <span>${escapeHtml(item.recommendation)}</span>
                          </div>
                          ${statusPill(item.status, item.severity)}
                        </article>
                      `,
                    )
                    .join("")
                : `<div class="empty-state">Критических задач нет.</div>`
            }
          </div>
        </section>

        <section class="panel">
          <div class="panel-title">
            <h3>Топ продаж</h3>
            <span>за месяц</span>
          </div>
          <div class="bar-list">
            ${
              data.top_sales?.length
                ? data.top_sales
                    .map(
                      (item) => `
                        <div class="bar-row">
                          <span>${escapeHtml(item.name)}</span>
                          <div><i style="width: ${(item.sold_month / maxSales) * 100}%"></i></div>
                          <strong>${escapeHtml(item.sold_month)} шт.</strong>
                        </div>
                      `,
                    )
                    .join("")
                : `<div class="empty-state">Загрузите Excel для графика.</div>`
            }
          </div>
        </section>
      </div>

      <section class="panel">
        <div class="panel-title">
          <h3>Прогноз по остаткам</h3>
          <span>по ближайшему риску</span>
        </div>
        ${forecastTable(data.forecast)}
      </section>

      ${typeof abcInsightTemplate === "function" ? abcInsightTemplate() : ""}
    </section>
  `;
}

function bindDashboard() {
  document.getElementById("refresh-dashboard").addEventListener("click", refreshDashboard);
  document.getElementById("abc-refresh-inline")?.addEventListener("click", loadAbc);
  document.getElementById("open-chat")?.addEventListener("click", () => {
    state.active = "chat";
    render();
  });
  if (!state.abc.loaded && !state.abc.loading && typeof loadAbc === "function") {
    loadAbc();
  }
}

function forecastTable(rows) {
  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>Товар</th>
          <th>Остаток</th>
          <th>Спрос/мес</th>
          <th>Дней осталось</th>
          <th>Статус AI</th>
          <th>Действие</th>
        </tr>
      </thead>
      <tbody>
        ${
          rows?.length
            ? rows
                .map(
                  (item) => `
                    <tr>
                      <td>
                        <strong>${escapeHtml(item.name)}</strong>
                        <span>${escapeHtml(item.category)}</span>
                      </td>
                      <td>${escapeHtml(item.stock)} шт.</td>
                      <td>${escapeHtml(item.avg_monthly_sales)} шт.</td>
                      <td>${escapeHtml(item.days_left ?? "-")}</td>
                      <td>${statusPill(item.status, item.severity)}</td>
                      <td>${escapeHtml(item.action)}</td>
                    </tr>
                  `,
                )
                .join("")
            : `<tr><td colspan="6">Нет данных для прогноза.</td></tr>`
        }
      </tbody>
    </table>
  `;
}

