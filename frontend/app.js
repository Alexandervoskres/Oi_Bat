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
  { id: "chat", label: "AI-советник", adminOnly: false },
  { id: "imports", label: "Excel и история", adminOnly: false },
  { id: "reports", label: "Отчеты", adminOnly: false },
  { id: "users", label: "Пользователи", adminOnly: true },
  { id: "settings", label: "Сервер", adminOnly: false },
];

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
    messages: [],
    loading: false,
    error: "",
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
  modal: {
    open: false,
    mode: "edit", // "edit" | "create"
    product: null,
    saving: false,
    error: "",
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

function button(label, className = "", attrs = "") {
  return `<button ${attrs} class="button ${className}"><span>${escapeHtml(label)}</span></button>`;
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
      if (state.active === "imports" && !state.imports.rows.length) await loadImports();
      if (state.active === "users" && !state.users.rows.length) await loadUsers();
    });
  });
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
  if (state.active === "chat") return chatTemplate();
  if (state.active === "imports") return importsTemplate();
  if (state.active === "reports") return reportsTemplate();
  if (state.active === "users" && state.user.role === "admin") return usersTemplate();
  return settingsTemplate();
}

function bindActiveScreen() {
  if (state.active === "dashboard") bindDashboard();
  if (state.active === "warehouse") bindWarehouse();
  if (state.active === "risks") bindRisks();
  if (state.active === "procurement") bindProcurement();
  if (state.active === "chat") bindChat();
  if (state.active === "imports") bindImports();
  if (state.active === "reports") bindReports();
  if (state.active === "users" && state.user.role === "admin") bindUsers();
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
    </section>
  `;
}

function bindDashboard() {
  document.getElementById("refresh-dashboard").addEventListener("click", refreshDashboard);
  document.getElementById("open-chat")?.addEventListener("click", () => {
    state.active = "chat";
    render();
  });
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

// ─── Warehouse ────────────────────────────────────────────────────────────────

function warehouseTemplate() {
  const model = state.warehouse;
  const statuses = ["", "Срочно заказать", "Нет в наличии", "Сделать скидку", "Мертвый груз", "Растущий спрос", "Норма"];
  const canEdit = ["admin", "manager"].includes(state.user.role);
  const isAdmin = state.user.role === "admin";
  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">товарная матрица</span>
          <h2>Склад</h2>
        </div>
        <div class="toolbar">
          <label class="search-field">
            <span>Поиск</span>
            <input id="warehouse-search" placeholder="Товар, артикул, категория" value="${escapeHtml(model.search)}" />
          </label>
          <select id="warehouse-status">
            ${statuses.map((item) => `<option value="${escapeHtml(item)}" ${model.status === item ? "selected" : ""}>${escapeHtml(item || "Все статусы")}</option>`).join("")}
          </select>
          ${button("Найти", "", 'type="button" id="warehouse-load"')}
          ${canEdit ? button("+ Создать товар", "button-secondary", 'type="button" id="warehouse-create"') : ""}
        </div>
      </header>

      <section class="panel">
        ${model.error ? `<div class="error-box">${escapeHtml(model.error)}</div>` : ""}
        ${
          model.loading
            ? `<div class="empty-state">Загружаю товары...</div>`
            : `
              <table class="data-table warehouse-table">
                <thead>
                  <tr>
                    <th>Товар</th>
                    <th>Категория</th>
                    <th>Остаток</th>
                    <th>Продано/мес</th>
                    <th>Маржа</th>
                    <th>Последняя продажа</th>
                    <th>AI-статус</th>
                    ${canEdit ? "<th></th>" : ""}
                  </tr>
                </thead>
                <tbody>
                  ${
                    model.rows.length
                      ? model.rows
                          .map(
                            (item) => `
                              <tr>
                                <td>
                                  <strong>${escapeHtml(item.name)}</strong>
                                  <span>${escapeHtml(item.sku)}</span>
                                  ${item.do_not_order ? `<span class="product-flag flag-no-order">не закупать</span>` : ""}
                                  ${item.is_seasonal ? `<span class="product-flag flag-seasonal">сезонный</span>` : ""}
                                  ${item.is_on_demand ? `<span class="product-flag flag-on-demand">под заказ</span>` : ""}
                                </td>
                                <td>${escapeHtml(item.category)}</td>
                                <td>${escapeHtml(item.stock)} шт.</td>
                                <td>${escapeHtml(item.sold_month)} шт.</td>
                                <td>${escapeHtml(item.margin_percent)}%</td>
                                <td>${escapeHtml(formatDate(item.last_sale_date))}</td>
                                <td>
                                  ${statusPill(item.status, item.severity)}
                                  ${item.is_manual_risk ? `<span class="manual-tag" title="Статус задан вручную">ручной</span>` : ""}
                                </td>
                                ${
                                  canEdit
                                    ? `<td class="row-actions">
                                        <button class="btn-icon btn-edit-product" data-id="${item.id}" title="Редактировать">✏️</button>
                                        ${isAdmin ? `<button class="btn-icon btn-delete-product" data-id="${item.id}" data-name="${escapeHtml(item.name)}" title="Удалить">🗑</button>` : ""}
                                      </td>`
                                    : ""
                                }
                              </tr>
                            `,
                          )
                          .join("")
                      : `<tr><td colspan="${canEdit ? 8 : 7}">Товаров пока нет.</td></tr>`
                  }
                </tbody>
              </table>
            `
        }
      </section>
    </section>
  `;
}

function bindWarehouse() {
  document.getElementById("warehouse-load").addEventListener("click", loadProducts);
  document.getElementById("warehouse-status").addEventListener("change", loadProducts);
  document.getElementById("warehouse-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadProducts();
  });
  document.getElementById("warehouse-create")?.addEventListener("click", openCreateModal);
  document.querySelectorAll(".btn-edit-product").forEach((btn) => {
    btn.addEventListener("click", () => openProductModal(Number(btn.dataset.id)));
  });
  document.querySelectorAll(".btn-delete-product").forEach((btn) => {
    btn.addEventListener("click", () => deleteProduct(Number(btn.dataset.id), btn.dataset.name));
  });
}

async function deleteProduct(productId, name) {
  if (!window.confirm(`Удалить товар «${name}»? Действие необратимо.`)) return;
  try {
    await api(`/api/products/${productId}`, { method: "DELETE" });
    state.warehouse.rows = state.warehouse.rows.filter((r) => r.id !== productId);
    render();
    await refreshDashboard();
  } catch (error) {
    state.warehouse.error = error.message;
    render();
  }
}

async function loadProducts() {
  state.warehouse.search = document.getElementById("warehouse-search")?.value ?? state.warehouse.search;
  state.warehouse.status = document.getElementById("warehouse-status")?.value ?? state.warehouse.status;
  state.warehouse.loading = true;
  state.warehouse.error = "";
  render();

  try {
    const params = new URLSearchParams();
    if (state.warehouse.search) params.set("search", state.warehouse.search);
    if (state.warehouse.status) params.set("status", state.warehouse.status);
    const response = await api(`/api/products?${params.toString()}`);
    state.warehouse.rows = await response.json();
  } catch (error) {
    state.warehouse.rows = [];
    state.warehouse.error = error.message;
  } finally {
    state.warehouse.loading = false;
    render();
  }
}

// ─── Product Modal ────────────────────────────────────────────────────────────

const BLANK_PRODUCT = {
  id: null,
  sku: "",
  name: "",
  category: "Без категории",
  stock: 0,
  sold_month: 0,
  avg_monthly_sales: 0,
  purchase_price: 0,
  sale_price: 0,
  last_sale_date: null,
  supplier: "",
  min_stock: 5,
  lead_time_days: 7,
  notes: "",
  do_not_order: false,
  is_seasonal: false,
  is_on_demand: false,
  risk_status_override: null,
  risk_priority: null,
  risk_note: "",
  excluded_from_ai: false,
  is_manual_risk: false,
  margin_percent: 0,
  status: "Норма",
  severity: "normal",
};

function openCreateModal() {
  state.modal = { open: true, mode: "create", product: { ...BLANK_PRODUCT }, saving: false, error: "" };
  render();
}

async function openProductModal(productId) {
  try {
    const response = await api(`/api/products/${productId}`);
    const product = await response.json();
    state.modal = { open: true, mode: "edit", product, saving: false, error: "" };
    render();
  } catch (error) {
    state.warehouse.error = error.message;
    render();
  }
}

function closeModal() {
  state.modal = { open: false, mode: "edit", product: null, saving: false, error: "" };
  render();
}

function dateInputValue(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function numField(id, label, value, attrs = "") {
  return `
    <label class="form-label">
      <span>${escapeHtml(label)}</span>
      <input id="${id}" type="number" value="${escapeHtml(value)}" ${attrs} />
    </label>
  `;
}

function modalTemplate() {
  const p = state.modal.product;
  if (!p) return "";
  const isCreate = state.modal.mode === "create";
  const canRisk = ["admin", "manager"].includes(state.user.role);
  const isAdmin = state.user.role === "admin";

  return `
    <div class="modal-overlay" id="modal-overlay">
      <div class="modal-panel" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div>
            <span class="eyebrow">${isCreate ? "новый товар" : "карточка товара"}</span>
            <h3>${isCreate ? "Создание товара" : escapeHtml(p.name)}</h3>
            ${!isCreate ? `<small style="color:var(--muted)">${escapeHtml(p.sku)}</small>` : ""}
            ${!isCreate && p.is_manual_risk ? `<div class="manual-banner">⚑ Статус риска переопределён вручную</div>` : ""}
          </div>
          <button class="modal-close" id="modal-close">✕</button>
        </div>

        ${state.modal.error ? `<div class="error-box" style="margin-bottom:14px">${escapeHtml(state.modal.error)}</div>` : ""}

        <form id="product-edit-form" class="product-form">
          <div class="form-grid-2">
            <label class="form-label">
              <span>Артикул (SKU)</span>
              <input id="pf-sku" value="${escapeHtml(p.sku)}" ${isCreate ? "" : ""} />
            </label>
            <label class="form-label">
              <span>Название</span>
              <input id="pf-name" value="${escapeHtml(p.name)}" />
            </label>
            <label class="form-label">
              <span>Категория</span>
              <input id="pf-category" value="${escapeHtml(p.category)}" />
            </label>
            <label class="form-label">
              <span>Поставщик</span>
              <input id="pf-supplier" value="${escapeHtml(p.supplier)}" />
            </label>
          </div>

          <div class="form-grid-3">
            ${numField("pf-stock", "Остаток", p.stock, 'min="0"')}
            ${numField("pf-sold-month", "Продано/мес", p.sold_month, 'min="0"')}
            ${numField("pf-avg", "Ср. продажи/мес", p.avg_monthly_sales, 'min="0" step="0.1"')}
            ${numField("pf-purchase", "Закупочная цена", p.purchase_price, 'min="0" step="0.01"')}
            ${numField("pf-sale", "Продажная цена", p.sale_price, 'min="0" step="0.01"')}
            <label class="form-label">
              <span>Последняя продажа</span>
              <input id="pf-last-sale" type="date" value="${dateInputValue(p.last_sale_date)}" />
            </label>
            ${numField("pf-min-stock", "Мин. остаток", p.min_stock, 'min="0"')}
            ${numField("pf-lead-time", "Срок поставки (дн.)", p.lead_time_days, 'min="1"')}
          </div>

          <label class="form-label">
            <span>Комментарий менеджера</span>
            <textarea id="pf-notes" rows="2" class="form-textarea">${escapeHtml(p.notes)}</textarea>
          </label>

          <div class="flag-group">
            <label class="flag-check">
              <input type="checkbox" id="pf-do-not-order" ${p.do_not_order ? "checked" : ""} />
              <span>Не закупать</span>
            </label>
            <label class="flag-check">
              <input type="checkbox" id="pf-is-seasonal" ${p.is_seasonal ? "checked" : ""} />
              <span>Сезонный</span>
            </label>
            <label class="flag-check">
              <input type="checkbox" id="pf-is-on-demand" ${p.is_on_demand ? "checked" : ""} />
              <span>Под заказ</span>
            </label>
          </div>

          ${
            !isCreate && canRisk
              ? `
            <fieldset class="risk-fieldset">
              <legend>Ручная корректировка риска</legend>
              <div class="form-grid-2">
                <label class="form-label">
                  <span>Статус (переопределение)</span>
                  <select id="pf-risk-status">
                    ${RISK_STATUS_OPTIONS.map((o) => `<option value="${o.code}" ${(p.risk_status_override || "") === o.code ? "selected" : ""}>${escapeHtml(o.label)}</option>`).join("")}
                  </select>
                </label>
                <label class="form-label">
                  <span>Приоритет</span>
                  <select id="pf-risk-priority">
                    <option value="" ${!p.risk_priority ? "selected" : ""}>— авто —</option>
                    ${["critical", "high", "medium", "low"].map((pr) => `<option value="${pr}" ${p.risk_priority === pr ? "selected" : ""}>${escapeHtml(PRIORITY_LABELS[pr])}</option>`).join("")}
                  </select>
                </label>
              </div>
              <label class="form-label">
                <span>Заметка по риску (заменит авто-рекомендацию)</span>
                <textarea id="pf-risk-note" rows="2" class="form-textarea">${escapeHtml(p.risk_note || "")}</textarea>
              </label>
              <label class="flag-check">
                <input type="checkbox" id="pf-excluded-ai" ${p.excluded_from_ai ? "checked" : ""} />
                <span>Исключить из AI-рекомендаций</span>
              </label>
            </fieldset>
          `
              : ""
          }

          ${
            !isCreate
              ? `
            <div class="modal-info-grid">
              <div><span>Маржа</span><strong>${escapeHtml(p.margin_percent)}%</strong></div>
              <div><span>AI-статус</span>${statusPill(p.status, p.severity)}</div>
            </div>
          `
              : ""
          }

          <div class="modal-actions">
            ${!isCreate && isAdmin ? `<button type="button" class="button button-danger" id="modal-delete"><span>Удалить</span></button>` : ""}
            <div class="modal-actions-right">
              <button type="button" class="button button-ghost" id="modal-cancel">Отмена</button>
              ${button(state.modal.saving ? "Сохраняю..." : isCreate ? "Создать" : "Сохранить", "", `type="submit" ${state.modal.saving ? "disabled" : ""}`)}
            </div>
          </div>
        </form>
      </div>
    </div>
  `;
}

function bindModal() {
  document.getElementById("modal-overlay").addEventListener("click", (e) => {
    if (e.target.id === "modal-overlay") closeModal();
  });
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
  document.getElementById("product-edit-form").addEventListener("submit", saveProduct);
  document.getElementById("modal-delete")?.addEventListener("click", () => {
    const p = state.modal.product;
    closeModal();
    deleteProduct(p.id, p.name);
  });

  const onKey = (e) => {
    if (e.key === "Escape") {
      closeModal();
      document.removeEventListener("keydown", onKey);
    }
  };
  document.addEventListener("keydown", onKey);
}

function readProductForm() {
  const get = (id) => document.getElementById(id);
  return {
    sku: get("pf-sku").value.trim(),
    name: get("pf-name").value.trim(),
    category: get("pf-category").value.trim() || "Без категории",
    supplier: get("pf-supplier").value.trim(),
    stock: Number(get("pf-stock").value),
    sold_month: Number(get("pf-sold-month").value),
    avg_monthly_sales: Number(get("pf-avg").value),
    purchase_price: Number(get("pf-purchase").value),
    sale_price: Number(get("pf-sale").value),
    last_sale_date: get("pf-last-sale").value || null,
    min_stock: Number(get("pf-min-stock").value),
    lead_time_days: Number(get("pf-lead-time").value),
    notes: get("pf-notes").value,
    do_not_order: get("pf-do-not-order").checked,
    is_seasonal: get("pf-is-seasonal").checked,
    is_on_demand: get("pf-is-on-demand").checked,
  };
}

function validateProductForm(form) {
  if (!form.sku) return "Укажите артикул (SKU).";
  if (!form.name) return "Укажите название товара.";
  const numbers = {
    "Остаток": form.stock,
    "Продано/мес": form.sold_month,
    "Ср. продажи": form.avg_monthly_sales,
    "Закупочная цена": form.purchase_price,
    "Продажная цена": form.sale_price,
    "Мин. остаток": form.min_stock,
  };
  for (const [label, value] of Object.entries(numbers)) {
    if (Number.isNaN(value) || value < 0) return `Поле «${label}» должно быть числом ≥ 0.`;
  }
  if (Number.isNaN(form.lead_time_days) || form.lead_time_days < 1) return "Срок поставки должен быть ≥ 1 дня.";
  return "";
}

async function saveProduct(event) {
  event.preventDefault();
  const isCreate = state.modal.mode === "create";
  const form = readProductForm();
  const validationError = validateProductForm(form);
  if (validationError) {
    state.modal.error = validationError;
    render();
    return;
  }

  // Capture the risk fields BEFORE render() rebuilds the DOM and resets them.
  let riskBody = null;
  const riskStatus = document.getElementById("pf-risk-status");
  if (!isCreate && riskStatus) {
    riskBody = {
      risk_status_override: riskStatus.value,
      risk_priority: document.getElementById("pf-risk-priority").value || null,
      risk_note: document.getElementById("pf-risk-note").value,
      excluded_from_ai: document.getElementById("pf-excluded-ai").checked,
    };
  }

  state.modal.saving = true;
  state.modal.error = "";
  render();

  try {
    if (isCreate) {
      await api("/api/products", { method: "POST", body: JSON.stringify(form) });
    } else {
      await api(`/api/products/${state.modal.product.id}`, { method: "PATCH", body: JSON.stringify(form) });
      if (riskBody) {
        await api(`/api/products/${state.modal.product.id}/risk`, { method: "PATCH", body: JSON.stringify(riskBody) });
      }
    }
    closeModal();
    if (state.active === "warehouse") await loadProducts();
    if (state.active === "risks") await loadRisks();
    await refreshDashboard();
  } catch (error) {
    state.modal.saving = false;
    state.modal.error = error.message;
    render();
  }
}

// ─── Procurement ──────────────────────────────────────────────────────────────

function procurementQty(item) {
  const override = state.procurement.quantities[item.id];
  return override !== undefined ? override : item.recommended_qty;
}

function procurementTemplate() {
  const model = state.procurement;
  const totalCost = model.rows.reduce((sum, r) => {
    return sum + procurementQty(r) * r.purchase_price;
  }, 0);
  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">план заказов</span>
          <h2>Закупки</h2>
        </div>
        <div class="toolbar">
          ${model.rows.length ? button("Скачать CSV", "button-secondary", 'type="button" id="procurement-csv"') : ""}
          ${button("Обновить", "", 'type="button" id="procurement-refresh"')}
        </div>
      </header>

      ${model.error ? `<div class="error-box" style="margin-bottom:14px">${escapeHtml(model.error)}</div>` : ""}

      ${
        model.rows.length
          ? `
          <div class="panel" style="margin-bottom:14px">
            <div class="procurement-summary">
              <div><span>Позиций к заказу</span><strong>${model.rows.length}</strong></div>
              <div><span>Сумма закупки</span><strong>${formatMoney(totalCost)}</strong></div>
              <div><span>Критичных</span><strong>${model.rows.filter((r) => r.severity === "critical").length}</strong></div>
            </div>
          </div>
        `
          : ""
      }

      <section class="panel">
        ${
          model.loading
            ? `<div class="empty-state">Строю план закупок...</div>`
            : model.rows.length
              ? `
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Товар</th>
                    <th>Остаток</th>
                    <th>Спрос/мес</th>
                    <th>Поставщик</th>
                    <th>Срок пост.</th>
                    <th>Кол-во к заказу</th>
                    <th>Сумма</th>
                    <th>Приоритет</th>
                  </tr>
                </thead>
                <tbody>
                  ${model.rows
                    .map(
                      (item) => {
                        const qty = procurementQty(item);
                        const cost = qty * item.purchase_price;
                        return `
                        <tr>
                          <td>
                            <strong>${escapeHtml(item.name)}</strong>
                            <span>${escapeHtml(item.category)}</span>
                            ${item.is_seasonal ? `<span class="product-flag flag-seasonal">сезонный</span>` : ""}
                            ${item.is_on_demand ? `<span class="product-flag flag-on-demand">под заказ</span>` : ""}
                          </td>
                          <td>${escapeHtml(item.stock)} шт.</td>
                          <td>${escapeHtml(item.avg_monthly_sales)} шт.</td>
                          <td>${escapeHtml(item.supplier || "—")}</td>
                          <td>${escapeHtml(item.lead_time_days)} дн.</td>
                          <td>
                            <input
                              class="qty-input"
                              type="number"
                              min="0"
                              value="${qty}"
                              data-id="${item.id}"
                              data-price="${item.purchase_price}"
                              title="Рекомендовано: ${item.recommended_qty} шт."
                            />
                          </td>
                          <td id="cost-${item.id}">${item.purchase_price ? formatMoney(cost) : "—"}</td>
                          <td>${statusPill(item.status, item.severity)}</td>
                        </tr>
                      `;
                      },
                    )
                    .join("")}
                </tbody>
              </table>
            `
              : `<div class="empty-state">Нет позиций, требующих закупки. Загрузите данные из Excel.</div>`
        }
      </section>
    </section>
  `;
}

function bindProcurement() {
  document.getElementById("procurement-refresh")?.addEventListener("click", loadProcurement);
  document.getElementById("procurement-csv")?.addEventListener("click", exportProcurementCsv);

  document.querySelectorAll(".qty-input").forEach((input) => {
    input.addEventListener("input", () => {
      const id = Number(input.dataset.id);
      const price = Number(input.dataset.price);
      const qty = Math.max(0, Number(input.value) || 0);
      state.procurement.quantities[id] = qty;
      const costEl = document.getElementById(`cost-${id}`);
      if (costEl) costEl.textContent = price ? formatMoney(qty * price) : "—";
      // update summary total live
      const totalEl = document.querySelector(".procurement-summary div:nth-child(2) strong");
      if (totalEl) {
        const total = state.procurement.rows.reduce((sum, r) => sum + procurementQty(r) * r.purchase_price, 0);
        totalEl.textContent = formatMoney(total);
      }
    });
  });
}

function exportProcurementCsv() {
  const rows = state.procurement.rows;
  if (!rows.length) return;

  const headers = ["Артикул", "Название", "Категория", "Поставщик", "Остаток", "Спрос/мес", "Срок поставки", "К заказу", "Цена закупки", "Сумма", "Приоритет"];
  const lines = [headers.join(";")];

  for (const r of rows) {
    const qty = procurementQty(r);
    lines.push([
      r.sku,
      r.name,
      r.category,
      r.supplier || "",
      r.stock,
      r.avg_monthly_sales,
      r.lead_time_days,
      qty,
      r.purchase_price,
      (qty * r.purchase_price).toFixed(2),
      r.status,
    ].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(";"));
  }

  const bom = "﻿";
  const blob = new Blob([bom + lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `zakupki-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function loadProcurement() {
  state.procurement.loading = true;
  state.procurement.error = "";
  render();
  try {
    const response = await api("/api/procurement");
    state.procurement.rows = await response.json();
  } catch (error) {
    state.procurement.error = error.message;
  } finally {
    state.procurement.loading = false;
    render();
  }
}

// ─── Risks ────────────────────────────────────────────────────────────────────

function isRiskRow(item) {
  return item.severity !== "normal" || item.is_manual_risk || item.do_not_order;
}

function filteredRiskRows() {
  const { status, priority, mode } = state.risks.filter;
  return state.risks.rows.filter((item) => {
    if (status && item.status !== status) return false;
    if (priority && item.risk_priority !== priority) return false;
    if (mode === "manual" && !item.is_manual_risk) return false;
    if (mode === "auto" && item.is_manual_risk) return false;
    return true;
  });
}

function risksTemplate() {
  const model = state.risks;
  const rows = filteredRiskRows();
  const canEdit = ["admin", "manager"].includes(state.user.role);
  const statuses = ["Срочно заказать", "Нет в наличии", "Сделать скидку", "Мертвый груз", "Растущий спрос", "Норма"];

  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">управление рисками</span>
          <h2>Риски</h2>
        </div>
        <div class="toolbar">
          <select id="risk-filter-status">
            <option value="">Все статусы</option>
            ${statuses.map((s) => `<option value="${escapeHtml(s)}" ${model.filter.status === s ? "selected" : ""}>${escapeHtml(s)}</option>`).join("")}
          </select>
          <select id="risk-filter-priority">
            <option value="">Все приоритеты</option>
            ${["critical", "high", "medium", "low"].map((pr) => `<option value="${pr}" ${model.filter.priority === pr ? "selected" : ""}>${escapeHtml(PRIORITY_LABELS[pr])}</option>`).join("")}
          </select>
          <select id="risk-filter-mode">
            <option value="">Все источники</option>
            <option value="manual" ${model.filter.mode === "manual" ? "selected" : ""}>Ручные</option>
            <option value="auto" ${model.filter.mode === "auto" ? "selected" : ""}>Авто</option>
          </select>
          ${button("Обновить", "button-secondary", 'type="button" id="risks-refresh"')}
        </div>
      </header>

      ${model.error ? `<div class="error-box" style="margin-bottom:14px">${escapeHtml(model.error)}</div>` : ""}
      ${model.message ? `<div class="notice-box" style="margin-bottom:14px">${escapeHtml(model.message)}</div>` : ""}

      <section class="panel">
        ${
          model.loading
            ? `<div class="empty-state">Загружаю риски...</div>`
            : rows.length
              ? `
              <table class="data-table risks-table">
                <thead>
                  <tr>
                    <th>Товар</th>
                    <th>Статус</th>
                    <th>Приоритет</th>
                    <th>Источник</th>
                    <th>Рекомендация</th>
                    ${canEdit ? "<th>Действия</th>" : ""}
                  </tr>
                </thead>
                <tbody>
                  ${rows
                    .map(
                      (item) => `
                      <tr>
                        <td>
                          <strong>${escapeHtml(item.name)}</strong>
                          <span>${escapeHtml(item.sku)} · ${escapeHtml(item.category)}</span>
                          ${item.do_not_order ? `<span class="product-flag flag-no-order">не закупать</span>` : ""}
                          ${item.excluded_from_ai ? `<span class="product-flag flag-no-order">скрыт из AI</span>` : ""}
                        </td>
                        <td>${statusPill(item.status, item.severity)}</td>
                        <td><span class="priority-tag priority-${escapeHtml(item.risk_priority)}">${escapeHtml(PRIORITY_LABELS[item.risk_priority] || item.risk_priority)}</span></td>
                        <td>${item.is_manual_risk ? `<span class="manual-tag">ручной</span>` : `<span style="color:var(--muted)">авто</span>`}</td>
                        <td class="risk-reco">${escapeHtml(item.recommendation)}</td>
                        ${
                          canEdit
                            ? `<td class="row-actions">
                                <button class="btn-mini btn-risk-order" data-id="${item.id}" title="В план закупок">Заказать</button>
                                <button class="btn-mini btn-risk-exclude" data-id="${item.id}" title="Скрыть из AI-рекомендаций">${item.excluded_from_ai ? "Вернуть в AI" : "Скрыть из AI"}</button>
                                <button class="btn-mini btn-risk-resolve" data-id="${item.id}" title="Отметить как решённый">Решено</button>
                                <button class="btn-mini btn-risk-edit" data-id="${item.id}" title="Редактировать риск">✏️</button>
                              </td>`
                            : ""
                        }
                      </tr>
                    `,
                    )
                    .join("")}
                </tbody>
              </table>
            `
              : `<div class="empty-state">Нет товаров с рисками по выбранным фильтрам.</div>`
        }
      </section>
    </section>
  `;
}

function bindRisks() {
  const apply = (key) => (e) => {
    state.risks.filter[key] = e.target.value;
    render();
  };
  document.getElementById("risk-filter-status")?.addEventListener("change", apply("status"));
  document.getElementById("risk-filter-priority")?.addEventListener("change", apply("priority"));
  document.getElementById("risk-filter-mode")?.addEventListener("change", apply("mode"));
  document.getElementById("risks-refresh")?.addEventListener("click", loadRisks);

  document.querySelectorAll(".btn-risk-edit").forEach((btn) => {
    btn.addEventListener("click", () => openRiskModal(Number(btn.dataset.id)));
  });
  document.querySelectorAll(".btn-risk-order").forEach((btn) => {
    btn.addEventListener("click", async () => {
      state.active = "procurement";
      render();
      await loadProcurement();
    });
  });
  document.querySelectorAll(".btn-risk-exclude").forEach((btn) => {
    btn.addEventListener("click", () => toggleExcludeFromAi(Number(btn.dataset.id)));
  });
  document.querySelectorAll(".btn-risk-resolve").forEach((btn) => {
    btn.addEventListener("click", () => resolveRisk(Number(btn.dataset.id)));
  });
}

async function loadRisks() {
  state.risks.loading = true;
  state.risks.error = "";
  render();
  try {
    const response = await api("/api/products");
    const all = await response.json();
    state.risks.rows = all.filter(isRiskRow);
  } catch (error) {
    state.risks.error = error.message;
  } finally {
    state.risks.loading = false;
    render();
  }
}

function findRiskRow(id) {
  return state.risks.rows.find((r) => r.id === id);
}

async function patchRisk(productId, body, successMessage) {
  try {
    const response = await api(`/api/products/${productId}/risk`, { method: "PATCH", body: JSON.stringify(body) });
    const updated = await response.json();
    const idx = state.risks.rows.findIndex((r) => r.id === productId);
    if (idx !== -1) {
      if (isRiskRow(updated)) state.risks.rows[idx] = updated;
      else state.risks.rows.splice(idx, 1);
    }
    state.risks.message = successMessage || "";
    render();
    await refreshDashboard();
  } catch (error) {
    state.risks.error = error.message;
    render();
  }
}

async function toggleExcludeFromAi(productId) {
  const row = findRiskRow(productId);
  if (!row) return;
  const next = !row.excluded_from_ai;
  await patchRisk(productId, { excluded_from_ai: next }, next ? "Товар скрыт из AI-рекомендаций." : "Товар возвращён в AI-рекомендации.");
}

async function resolveRisk(productId) {
  await patchRisk(
    productId,
    { risk_status_override: "ok", risk_resolved_at: new Date().toISOString() },
    "Риск отмечен как решённый.",
  );
}

// ─── Risk mini-modal ──────────────────────────────────────────────────────────

async function openRiskModal(productId) {
  let product = findRiskRow(productId);
  try {
    if (!product) {
      const response = await api(`/api/products/${productId}`);
      product = await response.json();
    }
    state.riskModal = { open: true, product, saving: false, error: "" };
    render();
  } catch (error) {
    state.risks.error = error.message;
    render();
  }
}

function closeRiskModal() {
  state.riskModal = { open: false, product: null, saving: false, error: "" };
  render();
}

function riskModalTemplate() {
  const p = state.riskModal.product;
  if (!p) return "";
  return `
    <div class="modal-overlay" id="risk-modal-overlay">
      <div class="modal-panel modal-panel-small" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div>
            <span class="eyebrow">риск товара</span>
            <h3>${escapeHtml(p.name)}</h3>
            <small style="color:var(--muted)">${escapeHtml(p.sku)}</small>
          </div>
          <button class="modal-close" id="risk-modal-close">✕</button>
        </div>

        ${state.riskModal.error ? `<div class="error-box" style="margin-bottom:14px">${escapeHtml(state.riskModal.error)}</div>` : ""}

        <form id="risk-form" class="product-form">
          <div class="form-grid-2">
            <label class="form-label">
              <span>Статус (переопределение)</span>
              <select id="rf-status">
                ${RISK_STATUS_OPTIONS.map((o) => `<option value="${o.code}" ${(p.risk_status_override || "") === o.code ? "selected" : ""}>${escapeHtml(o.label)}</option>`).join("")}
              </select>
            </label>
            <label class="form-label">
              <span>Приоритет</span>
              <select id="rf-priority">
                <option value="">— авто —</option>
                ${["critical", "high", "medium", "low"].map((pr) => `<option value="${pr}" ${p.risk_priority === pr ? "selected" : ""}>${escapeHtml(PRIORITY_LABELS[pr])}</option>`).join("")}
              </select>
            </label>
          </div>
          <label class="form-label">
            <span>Заметка по риску</span>
            <textarea id="rf-note" rows="3" class="form-textarea">${escapeHtml(p.risk_note || "")}</textarea>
          </label>
          <div class="flag-group">
            <label class="flag-check">
              <input type="checkbox" id="rf-excluded" ${p.excluded_from_ai ? "checked" : ""} />
              <span>Исключить из AI</span>
            </label>
            <label class="flag-check">
              <input type="checkbox" id="rf-do-not-order" ${p.do_not_order ? "checked" : ""} />
              <span>Не закупать</span>
            </label>
          </div>
          <div class="modal-actions">
            <div class="modal-actions-right">
              <button type="button" class="button button-ghost" id="risk-modal-cancel">Отмена</button>
              ${button(state.riskModal.saving ? "Сохраняю..." : "Сохранить", "", `type="submit" ${state.riskModal.saving ? "disabled" : ""}`)}
            </div>
          </div>
        </form>
      </div>
    </div>
  `;
}

function bindRiskModal() {
  document.getElementById("risk-modal-overlay").addEventListener("click", (e) => {
    if (e.target.id === "risk-modal-overlay") closeRiskModal();
  });
  document.getElementById("risk-modal-close").addEventListener("click", closeRiskModal);
  document.getElementById("risk-modal-cancel").addEventListener("click", closeRiskModal);
  document.getElementById("risk-form").addEventListener("submit", saveRiskModal);

  const onKey = (e) => {
    if (e.key === "Escape") {
      closeRiskModal();
      document.removeEventListener("keydown", onKey);
    }
  };
  document.addEventListener("keydown", onKey);
}

async function saveRiskModal(event) {
  event.preventDefault();
  const productId = state.riskModal.product.id;

  // Read the form BEFORE re-rendering — render() rebuilds the DOM and would
  // reset the inputs to the saved product values, losing the user's edits.
  const body = {
    risk_status_override: document.getElementById("rf-status").value,
    risk_priority: document.getElementById("rf-priority").value || null,
    risk_note: document.getElementById("rf-note").value,
    excluded_from_ai: document.getElementById("rf-excluded").checked,
    do_not_order: document.getElementById("rf-do-not-order").checked,
  };

  state.riskModal.saving = true;
  state.riskModal.error = "";
  render();

  try {
    const response = await api(`/api/products/${productId}/risk`, { method: "PATCH", body: JSON.stringify(body) });
    const updated = await response.json();
    const idx = state.risks.rows.findIndex((r) => r.id === productId);
    if (idx !== -1) {
      if (isRiskRow(updated)) state.risks.rows[idx] = updated;
      else state.risks.rows.splice(idx, 1);
    }
    closeRiskModal();
    await refreshDashboard();
  } catch (error) {
    state.riskModal.saving = false;
    state.riskModal.error = error.message;
    render();
  }
}

// ─── AI Chat ──────────────────────────────────────────────────────────────────

const CHAT_QUICK_QUESTIONS = [
  "Что заказать?",
  "Что распродать?",
  "План на неделю",
  "Риски склада",
  "Заказ на 100 000 ₽",
];

function chatTemplate() {
  const model = state.chat;
  return `
    <section class="screen chat-screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">ассистент склада</span>
          <h2>AI-советник</h2>
        </div>
      </header>

      <section class="panel chat-panel">
        <div class="chat-messages" id="chat-messages">
          ${
            model.messages.length
              ? model.messages
                  .map(
                    (m) => `
                    <div class="chat-msg chat-msg-${m.role}">
                      <div class="chat-bubble">${chatBubbleContent(m)}</div>
                    </div>
                  `,
                  )
                  .join("")
              : `<div class="chat-empty">Задайте вопрос о складе, закупках или рисках — например «Что заказать на этой неделе?»</div>`
          }
          ${model.loading ? `<div class="chat-msg chat-msg-assistant"><div class="chat-bubble chat-typing"><span></span><span></span><span></span></div></div>` : ""}
        </div>

        ${model.error ? `<div class="error-box" style="margin:12px 0">${escapeHtml(model.error)}</div>` : ""}

        <div class="chat-quick">
          ${CHAT_QUICK_QUESTIONS.map((q) => `<button class="chat-chip" data-q="${escapeHtml(q)}">${escapeHtml(q)}</button>`).join("")}
        </div>

        <form id="chat-form" class="chat-input-row">
          <textarea id="chat-input" rows="1" placeholder="Спросите AI-советника..." ${model.loading ? "disabled" : ""}></textarea>
          ${button(model.loading ? "..." : "Отправить", "", `type="submit" ${model.loading ? "disabled" : ""}`)}
        </form>
      </section>
    </section>
  `;
}

function chatBubbleContent(message) {
  const text = escapeHtml(message.text).replaceAll("\n", "<br>");
  let actions = "";
  if (message.role === "assistant" && message.suggested_actions?.length) {
    actions = `<div class="chat-actions">${message.suggested_actions.map((a) => `<span class="chat-action-tag">${escapeHtml(a)}</span>`).join("")}</div>`;
  }
  return text + actions;
}

function bindChat() {
  const form = document.getElementById("chat-form");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const input = document.getElementById("chat-input");
    sendChat(input.value);
  });
  document.querySelectorAll(".chat-chip").forEach((chip) => {
    chip.addEventListener("click", () => sendChat(chip.dataset.q));
  });

  const messagesEl = document.getElementById("chat-messages");
  if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;

  const input = document.getElementById("chat-input");
  if (input && !state.chat.loading) input.focus();
}

async function sendChat(rawMessage) {
  const message = (rawMessage || "").trim();
  if (!message || state.chat.loading) return;

  state.chat.messages.push({ role: "user", text: message });
  state.chat.loading = true;
  state.chat.error = "";
  render();

  try {
    const response = await api("/api/ai/chat", { method: "POST", body: JSON.stringify({ message }) });
    const data = await response.json();
    state.chat.messages.push({
      role: "assistant",
      text: data.answer,
      suggested_actions: data.suggested_actions || [],
      used_products: data.used_products || [],
    });
  } catch (error) {
    state.chat.error = error.message;
  } finally {
    state.chat.loading = false;
    render();
  }
}

// ─── Imports ──────────────────────────────────────────────────────────────────

function importsTemplate() {
  const model = state.imports;
  const canUpload = ["admin", "manager"].includes(state.user.role);
  const hasPreview = !!model.preview;
  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">источник данных</span>
          <h2>Excel и история загрузок</h2>
        </div>
        ${button("Скачать шаблон", "", 'type="button" id="download-template"')}
      </header>

      <section class="upload-panel">
        <form id="upload-form">
          <label class="dropzone ${canUpload ? "" : "disabled"}">
            <strong>${escapeHtml(model.file ? model.file.name : "Выберите Excel-файл")}</strong>
            <span>${canUpload ? "Поддерживаются .xlsx и .xls с колонками из шаблона" : "У вашей роли нет прав на загрузку"}</span>
            <input id="upload-file" type="file" accept=".xlsx,.xls" ${canUpload ? "" : "disabled"} />
          </label>
          <div class="upload-buttons">
            ${button(model.previewing ? "Анализирую..." : "Предпросмотр", "button-secondary", `type="button" id="preview-btn" ${model.file && !model.previewing && !model.loading && canUpload ? "" : "disabled"}`)}
            ${button(model.loading ? "Загружаю..." : "Импортировать", "", `type="submit" ${model.file && !model.loading && !model.previewing && canUpload ? "" : "disabled"}`)}
          </div>
        </form>
        ${model.message ? `<div class="notice-box">${escapeHtml(model.message)}</div>` : ""}
      </section>

      ${hasPreview ? importPreviewTemplate(model.preview) : ""}

      <section class="panel">
        <div class="panel-title">
          <h3>История загрузок</h3>
          <span>${escapeHtml(model.rows.length)} файлов</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Дата</th>
              <th>Файл</th>
              <th>Строк</th>
              <th>Источник</th>
            </tr>
          </thead>
          <tbody>
            ${
              model.rows.length
                ? model.rows
                    .map(
                      (item) => `
                        <tr>
                          <td>${escapeHtml(formatDate(item.created_at))}</td>
                          <td>${escapeHtml(item.filename)}</td>
                          <td>${escapeHtml(item.rows_count)}</td>
                          <td>${escapeHtml(item.source)}</td>
                        </tr>
                      `,
                    )
                    .join("")
                : `<tr><td colspan="4">Загрузок пока нет.</td></tr>`
            }
          </tbody>
        </table>
      </section>
    </section>
  `;
}

function importPreviewTemplate(preview) {
  const FIELD_LABELS = {
    sku: "Артикул", name: "Название", category: "Категория", stock: "Остаток",
    sold_month: "Продажи/мес", avg_monthly_sales: "Ср. продажи", purchase_price: "Закупочная цена",
    sale_price: "Продажная цена", last_sale_date: "Дата продажи", supplier: "Поставщик",
    min_stock: "Мин. остаток", lead_time_days: "Срок поставки",
  };
  return `
    <section class="panel preview-panel">
      <div class="panel-title">
        <h3>Предпросмотр импорта</h3>
        <button class="modal-close" id="close-preview" title="Закрыть">✕</button>
      </div>

      <div class="preview-stats">
        <div class="preview-stat preview-stat-new"><span>Новых</span><strong>+${preview.new_count}</strong></div>
        <div class="preview-stat preview-stat-update"><span>Обновится</span><strong>↻ ${preview.update_count}</strong></div>
        <div class="preview-stat ${preview.error_count ? "preview-stat-error" : ""}"><span>Ошибки</span><strong>${preview.error_count}</strong></div>
        <div class="preview-stat"><span>Всего строк</span><strong>${preview.total_rows}</strong></div>
      </div>

      <div class="preview-cols">
        <div>
          <strong>Распознаны колонки:</strong>
          ${preview.columns_found.map((c) => `<span class="col-tag col-found">${escapeHtml(FIELD_LABELS[c] || c)}</span>`).join("")}
        </div>
        ${preview.columns_missing.length ? `
        <div>
          <strong>Не найдены:</strong>
          ${preview.columns_missing.map((c) => `<span class="col-tag col-missing">${escapeHtml(FIELD_LABELS[c] || c)}</span>`).join("")}
        </div>` : ""}
      </div>

      ${preview.warnings.length ? `
        <div class="preview-warnings">
          ${preview.warnings.slice(0, 5).map((w) => `<div>⚠ ${escapeHtml(w)}</div>`).join("")}
          ${preview.warnings.length > 5 ? `<div>... и ещё ${preview.warnings.length - 5} предупреждений</div>` : ""}
        </div>
      ` : ""}

      <table class="data-table" style="margin-top:14px">
        <thead>
          <tr><th>#</th><th>Артикул</th><th>Название</th><th>Действие</th></tr>
        </thead>
        <tbody>
          ${preview.preview_rows
            .map(
              (row) => `
              <tr class="${row.action === "error" ? "preview-row-error" : ""}">
                <td>${escapeHtml(row.row_number)}</td>
                <td>${escapeHtml(row.sku || "—")}</td>
                <td>${escapeHtml(row.name)}${row.error ? `<span style="color:var(--danger)"> — ${escapeHtml(row.error)}</span>` : ""}</td>
                <td>
                  ${row.action === "create" ? `<span style="color:var(--green)">Создать</span>` : ""}
                  ${row.action === "update" ? `<span style="color:var(--yellow)">Обновить</span>` : ""}
                  ${row.action === "error" ? `<span style="color:var(--danger)">Пропустить</span>` : ""}
                </td>
              </tr>
            `,
            )
            .join("")}
        </tbody>
      </table>
    </section>
  `;
}

function bindImports() {
  document.getElementById("download-template").addEventListener("click", downloadTemplate);
  document.getElementById("upload-file")?.addEventListener("change", (event) => {
    state.imports.file = event.target.files?.[0] || null;
    state.imports.preview = null;
    render();
  });
  document.getElementById("preview-btn")?.addEventListener("click", previewImport);
  document.getElementById("upload-form").addEventListener("submit", uploadFile);
  document.getElementById("close-preview")?.addEventListener("click", () => {
    state.imports.preview = null;
    render();
  });
}

async function loadImports() {
  try {
    const response = await api("/api/imports");
    state.imports.rows = await response.json();
  } catch (error) {
    state.imports.message = error.message;
  }
  render();
}

async function previewImport() {
  if (!state.imports.file) return;
  state.imports.previewing = true;
  state.imports.preview = null;
  state.imports.message = "";
  render();
  try {
    const body = new FormData();
    body.append("file", state.imports.file);
    const response = await api("/api/imports/preview", { method: "POST", body });
    state.imports.preview = await response.json();
  } catch (error) {
    state.imports.message = error.message;
  } finally {
    state.imports.previewing = false;
    render();
  }
}

async function uploadFile(event) {
  event.preventDefault();
  if (!state.imports.file) return;
  state.imports.loading = true;
  state.imports.message = "";
  render();
  try {
    const body = new FormData();
    body.append("file", state.imports.file);
    const response = await api("/api/imports/upload", { method: "POST", body });
    const result = await response.json();
    state.imports.file = null;
    state.imports.preview = null;
    state.imports.message = `Импортировано ${result.imported} строк. Новых: ${result.created}, обновлено: ${result.updated}.`;
    await loadImports();
    await refreshDashboard();
  } catch (error) {
    state.imports.message = error.message;
  } finally {
    state.imports.loading = false;
    render();
  }
}

async function downloadTemplate() {
  const response = await api("/api/imports/template.xlsx");
  await downloadBlob(response, "skladai-template.xlsx");
}

// ─── Reports ──────────────────────────────────────────────────────────────────

function reportsTemplate() {
  const metrics = state.dashboard.metrics;
  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">выгрузка</span>
          <h2>PDF-отчеты</h2>
        </div>
        ${button("Скачать PDF", "", 'type="button" id="download-pdf"')}
      </header>

      <section class="panel report-panel">
        <div>
          <h3>Отчет по рискам</h3>
          <p>PDF включает товары, где AI-статус требует действия: срочная закупка, отсутствие остатка, мертвый груз или скидка.</p>
        </div>
        <div class="report-stats">
          ${metricTemplate("Закупка", metrics.low_stock, "критичные позиции")}
          ${metricTemplate("Скидки", metrics.dead_stock, "залежавшиеся позиции")}
        </div>
      </section>
    </section>
  `;
}

function bindReports() {
  document.getElementById("download-pdf").addEventListener("click", async () => {
    const response = await api("/api/reports/risk.pdf");
    await downloadBlob(response, "skladai-risk-report.pdf");
  });
}

async function downloadBlob(response, filename) {
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// ─── Users ────────────────────────────────────────────────────────────────────

function usersTemplate() {
  const model = state.users;
  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">доступы</span>
          <h2>Пользователи и роли</h2>
        </div>
      </header>

      <div class="two-column">
        <section class="panel">
          <div class="panel-title"><h3>Создать пользователя</h3></div>
          <form id="user-form" class="user-form">
            <input id="user-username" placeholder="Логин" value="${escapeHtml(model.form.username)}" />
            <input id="user-full-name" placeholder="Имя" value="${escapeHtml(model.form.full_name)}" />
            <input id="user-password" type="password" placeholder="Пароль" value="${escapeHtml(model.form.password)}" />
            <select id="user-role">
              ${["manager", "buyer", "admin"].map((role) => `<option value="${role}" ${model.form.role === role ? "selected" : ""}>${escapeHtml(ROLE_LABELS[role])}</option>`).join("")}
            </select>
            ${button("Создать", "", 'type="submit"')}
          </form>
          ${model.message ? `<div class="notice-box">${escapeHtml(model.message)}</div>` : ""}
        </section>
        <section class="panel">
          <div class="panel-title">
            <h3>Список пользователей</h3>
            <span>${escapeHtml(model.rows.length)}</span>
          </div>
          <table class="data-table">
            <thead>
              <tr>
                <th>Логин</th>
                <th>Имя</th>
                <th>Роль</th>
                <th>Создан</th>
              </tr>
            </thead>
            <tbody>
              ${
                model.rows.length
                  ? model.rows
                      .map(
                        (item) => `
                          <tr>
                            <td>${escapeHtml(item.username)}</td>
                            <td>${escapeHtml(item.full_name)}</td>
                            <td>${escapeHtml(ROLE_LABELS[item.role] || item.role)}</td>
                            <td>${escapeHtml(formatDate(item.created_at))}</td>
                          </tr>
                        `,
                      )
                      .join("")
                  : `<tr><td colspan="4">Пользователей пока нет.</td></tr>`
              }
            </tbody>
          </table>
        </section>
      </div>
    </section>
  `;
}

function bindUsers() {
  document.getElementById("user-form").addEventListener("submit", createUser);
}

async function loadUsers() {
  try {
    const response = await api("/api/users");
    state.users.rows = await response.json();
  } catch (error) {
    state.users.message = error.message;
  }
  render();
}

async function createUser(event) {
  event.preventDefault();
  state.users.form = {
    username: document.getElementById("user-username").value,
    full_name: document.getElementById("user-full-name").value,
    password: document.getElementById("user-password").value,
    role: document.getElementById("user-role").value,
  };
  state.users.message = "";
  try {
    await api("/api/users", { method: "POST", body: JSON.stringify(state.users.form) });
    state.users.form = { username: "", full_name: "", password: "", role: "manager" };
    state.users.message = "Пользователь создан.";
    await loadUsers();
  } catch (error) {
    state.users.message = error.message;
    render();
  }
}

// ─── Settings ─────────────────────────────────────────────────────────────────

function settingsTemplate() {
  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">инфраструктура</span>
          <h2>Серверные настройки</h2>
        </div>
      </header>
      <section class="panel settings-list">
        <article>
          <strong>PostgreSQL</strong>
          <span>Основной режим через DATABASE_URL. Для локального старта есть fallback SQLite.</span>
        </article>
        <article>
          <strong>Claude API</strong>
          <span>Переменные CLAUDE_ENABLED, CLAUDE_API_KEY, CLAUDE_MODEL уже заложены в backend.</span>
        </article>
        <article>
          <strong>Деплой</strong>
          <span>Перед сервером замените SECRET_KEY, DEFAULT_ADMIN_PASSWORD и DATABASE_URL.</span>
        </article>
      </section>
    </section>
  `;
}

render();
