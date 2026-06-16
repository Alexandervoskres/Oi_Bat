// Part of СкладAI frontend. Loaded as an ordered classic script (see index.html).
// Shares globals (state, render, helpers) defined in core.js.

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

// ─── Audit ────────────────────────────────────────────────────────────────────

function auditTemplate() {
  const model = state.audit;
  const actions = Object.keys(AUDIT_ACTION_LABELS);
  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">журнал действий</span>
          <h2>Аудит</h2>
        </div>
        <div class="toolbar">
          <select id="audit-filter-action">
            <option value="">Все действия</option>
            ${actions.map((a) => `<option value="${a}" ${model.filter.action === a ? "selected" : ""}>${escapeHtml(AUDIT_ACTION_LABELS[a])}</option>`).join("")}
          </select>
          ${button("Обновить", "button-secondary", 'type="button" id="audit-refresh"')}
        </div>
      </header>

      ${model.error ? `<div class="error-box" style="margin-bottom:14px">${escapeHtml(model.error)}</div>` : ""}

      <section class="panel">
        ${
          model.loading
            ? `<div class="empty-state">Загружаю журнал...</div>`
            : model.rows.length
              ? `
              <table class="data-table audit-table">
                <thead>
                  <tr><th>Когда</th><th>Пользователь</th><th>Действие</th><th>Объект</th><th>Детали</th></tr>
                </thead>
                <tbody>
                  ${model.rows
                    .map(
                      (row) => `
                      <tr>
                        <td>${escapeHtml(formatDateTime(row.created_at))}</td>
                        <td>${escapeHtml(row.username || "—")}</td>
                        <td><span class="audit-action">${escapeHtml(AUDIT_ACTION_LABELS[row.action] || row.action)}</span></td>
                        <td>${escapeHtml(row.entity_type || "")}${row.entity_id ? ` #${escapeHtml(row.entity_id)}` : ""}</td>
                        <td class="audit-detail">${escapeHtml(row.detail || "")}</td>
                      </tr>
                    `,
                    )
                    .join("")}
                </tbody>
              </table>
            `
              : `<div class="empty-state">Записей пока нет.</div>`
        }
      </section>
    </section>
  `;
}

function bindAudit() {
  document.getElementById("audit-refresh")?.addEventListener("click", loadAudit);
  document.getElementById("audit-filter-action")?.addEventListener("change", (e) => {
    state.audit.filter.action = e.target.value;
    loadAudit();
  });
}

async function loadAudit() {
  state.audit.loading = true;
  state.audit.error = "";
  render();
  try {
    const params = new URLSearchParams();
    if (state.audit.filter.action) params.set("action", state.audit.filter.action);
    const response = await api(`/api/audit?${params.toString()}`);
    state.audit.rows = await response.json();
  } catch (error) {
    state.audit.error = error.message;
  } finally {
    state.audit.loading = false;
    render();
  }
}

// ─── Suppliers ────────────────────────────────────────────────────────────────

function reliabilityStars(n) {
  const full = Math.max(0, Math.min(5, Number(n) || 0));
  return "★".repeat(full) + "☆".repeat(5 - full);
}

function suppliersTemplate() {
  const model = state.suppliers;
  const canEdit = ["admin", "manager"].includes(state.user.role);
  const isAdmin = state.user.role === "admin";
  const f = model.form;
  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">справочник</span>
          <h2>Поставщики</h2>
        </div>
        ${button("Обновить", "button-secondary", 'type="button" id="suppliers-refresh"')}
      </header>

      ${model.error ? `<div class="error-box" style="margin-bottom:14px">${escapeHtml(model.error)}</div>` : ""}
      ${model.message ? `<div class="notice-box" style="margin-bottom:14px">${escapeHtml(model.message)}</div>` : ""}

      <div class="two-column">
        ${
          canEdit
            ? `
          <section class="panel">
            <div class="panel-title"><h3>${model.editingId ? "Редактирование поставщика" : "Новый поставщик"}</h3></div>
            <form id="supplier-form" class="supplier-form">
              <input id="sup-name" placeholder="Название*" value="${escapeHtml(f.name)}" />
              <input id="sup-contact" placeholder="Контактное лицо" value="${escapeHtml(f.contact_person)}" />
              <div class="form-grid-2">
                <input id="sup-phone" placeholder="Телефон" value="${escapeHtml(f.phone)}" />
                <input id="sup-email" placeholder="Email" value="${escapeHtml(f.email)}" />
              </div>
              <div class="form-grid-2">
                <label class="form-label"><span>Надёжность (1–5)</span><input id="sup-reliability" type="number" min="1" max="5" value="${escapeHtml(f.reliability)}" /></label>
                <label class="form-label"><span>Срок поставки (дн.)</span><input id="sup-lead" type="number" min="1" value="${escapeHtml(f.lead_time_days)}" /></label>
              </div>
              <label class="form-label"><span>Мин. сумма заказа</span><input id="sup-minorder" type="number" min="0" value="${escapeHtml(f.min_order_amount)}" /></label>
              <input id="sup-payment" placeholder="Условия оплаты" value="${escapeHtml(f.payment_terms)}" />
              <textarea id="sup-notes" rows="2" class="form-textarea" placeholder="Заметки">${escapeHtml(f.notes)}</textarea>
              <div class="modal-actions-right">
                ${model.editingId ? button("Отмена", "button-ghost", 'type="button" id="supplier-cancel"') : ""}
                ${button(model.editingId ? "Сохранить" : "Создать", "", 'type="submit"')}
              </div>
            </form>
          </section>
        `
            : ""
        }
        <section class="panel">
          <div class="panel-title">
            <h3>Список поставщиков</h3>
            <span>${escapeHtml(model.rows.length)}</span>
          </div>
          ${
            model.loading
              ? `<div class="empty-state">Загружаю...</div>`
              : model.rows.length
                ? `
                <table class="data-table suppliers-table">
                  <thead>
                    <tr><th>Поставщик</th><th>Надёжность</th><th>Срок</th><th>Товаров</th>${canEdit ? "<th></th>" : ""}</tr>
                  </thead>
                  <tbody>
                    ${model.rows
                      .map(
                        (s) => `
                        <tr>
                          <td>
                            <strong>${escapeHtml(s.name)}</strong>
                            <span>${escapeHtml([s.contact_person, s.phone, s.email].filter(Boolean).join(" · ") || "—")}</span>
                            ${s.payment_terms ? `<span>Оплата: ${escapeHtml(s.payment_terms)}</span>` : ""}
                          </td>
                          <td><span class="reliability-stars" title="${escapeHtml(s.reliability)}/5">${reliabilityStars(s.reliability)}</span></td>
                          <td>${escapeHtml(s.lead_time_days)} дн.</td>
                          <td>${escapeHtml(s.product_count)}</td>
                          ${
                            canEdit
                              ? `<td class="row-actions">
                                  <button class="btn-icon btn-supplier-edit" data-id="${s.id}" title="Редактировать">✏️</button>
                                  ${isAdmin ? `<button class="btn-icon btn-supplier-delete" data-id="${s.id}" data-name="${escapeHtml(s.name)}" title="Удалить">🗑</button>` : ""}
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
                : `<div class="empty-state">Поставщиков пока нет.</div>`
          }
        </section>
      </div>
    </section>
  `;
}

function bindSuppliers() {
  document.getElementById("suppliers-refresh")?.addEventListener("click", loadSuppliers);
  document.getElementById("supplier-form")?.addEventListener("submit", saveSupplier);
  document.getElementById("supplier-cancel")?.addEventListener("click", () => {
    resetSupplierForm();
    render();
  });
  document.querySelectorAll(".btn-supplier-edit").forEach((btn) => {
    btn.addEventListener("click", () => startEditSupplier(Number(btn.dataset.id)));
  });
  document.querySelectorAll(".btn-supplier-delete").forEach((btn) => {
    btn.addEventListener("click", () => deleteSupplier(Number(btn.dataset.id), btn.dataset.name));
  });
}

function resetSupplierForm() {
  state.suppliers.editingId = null;
  state.suppliers.form = { name: "", contact_person: "", phone: "", email: "", reliability: 3, min_order_amount: 0, payment_terms: "", lead_time_days: 7, notes: "" };
}

function startEditSupplier(id) {
  const s = state.suppliers.rows.find((r) => r.id === id);
  if (!s) return;
  state.suppliers.editingId = id;
  state.suppliers.form = {
    name: s.name, contact_person: s.contact_person, phone: s.phone, email: s.email,
    reliability: s.reliability, min_order_amount: s.min_order_amount, payment_terms: s.payment_terms,
    lead_time_days: s.lead_time_days, notes: s.notes,
  };
  state.suppliers.message = "";
  render();
}

function readSupplierForm() {
  return {
    name: document.getElementById("sup-name").value.trim(),
    contact_person: document.getElementById("sup-contact").value.trim(),
    phone: document.getElementById("sup-phone").value.trim(),
    email: document.getElementById("sup-email").value.trim(),
    reliability: Number(document.getElementById("sup-reliability").value),
    lead_time_days: Number(document.getElementById("sup-lead").value),
    min_order_amount: Number(document.getElementById("sup-minorder").value),
    payment_terms: document.getElementById("sup-payment").value.trim(),
    notes: document.getElementById("sup-notes").value,
  };
}

async function loadSuppliers() {
  state.suppliers.loading = true;
  state.suppliers.error = "";
  render();
  try {
    const response = await api("/api/suppliers");
    state.suppliers.rows = await response.json();
  } catch (error) {
    state.suppliers.error = error.message;
  } finally {
    state.suppliers.loading = false;
    render();
  }
}

async function saveSupplier(event) {
  event.preventDefault();
  const form = readSupplierForm();
  if (!form.name) {
    state.suppliers.error = "Укажите название поставщика.";
    render();
    return;
  }
  if (form.reliability < 1 || form.reliability > 5) {
    state.suppliers.error = "Надёжность должна быть от 1 до 5.";
    render();
    return;
  }

  const editingId = state.suppliers.editingId;
  state.suppliers.error = "";
  state.suppliers.message = "";
  try {
    if (editingId) {
      await api(`/api/suppliers/${editingId}`, { method: "PATCH", body: JSON.stringify(form) });
      state.suppliers.message = "Поставщик обновлён.";
    } else {
      await api("/api/suppliers", { method: "POST", body: JSON.stringify(form) });
      state.suppliers.message = "Поставщик создан.";
    }
    resetSupplierForm();
    await loadSuppliers();
  } catch (error) {
    state.suppliers.error = error.message;
    render();
  }
}

async function deleteSupplier(id, name) {
  if (!window.confirm(`Удалить поставщика «${name}»? Товары будут отвязаны.`)) return;
  try {
    await api(`/api/suppliers/${id}`, { method: "DELETE" });
    if (state.suppliers.editingId === id) resetSupplierForm();
    await loadSuppliers();
  } catch (error) {
    state.suppliers.error = error.message;
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
          <strong>AI-ассистент</strong>
          <span>Основной AI подключается через локальный агент StoreAI. Если агент недоступен, чат использует встроенные складские правила.</span>
        </article>
        <article>
          <strong>Деплой</strong>
          <span>Перед сервером замените SECRET_KEY, DEFAULT_ADMIN_PASSWORD и DATABASE_URL.</span>
        </article>
      </section>
    </section>
  `;
}

