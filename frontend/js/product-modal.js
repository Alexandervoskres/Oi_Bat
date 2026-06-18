// Часть фронтенда СкладAI. Грузится как обычный <script> (порядок — в index.html).
// Общие глобалы (state, render, api, помощники) объявлены в core.js.
//
// Этот файл — КАРТОЧКА ТОВАРА (модальное окно): создание и редактирование
// товара, секция «Движения склада», валидация формы и сохранение.
// Открывается с экрана «Склад» (warehouse.js) кнопками ✏️ / «+ Создать товар».

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
  supplier_id: null,
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

function ensureSuppliersLoaded() {
  // Populate the supplier dropdown in the product card without blocking it.
  if (!state.suppliers.rows.length) {
    loadSuppliersQuiet();
  }
}

async function loadSuppliersQuiet() {
  try {
    const response = await api("/api/suppliers");
    state.suppliers.rows = await response.json();
    if (state.modal.open) render();
  } catch (_) {
    // Non-fatal: the card still works, just without the supplier dropdown list.
  }
}

function openCreateModal() {
  state.modal = {
    open: true, mode: "create", product: { ...BLANK_PRODUCT },
    saving: false, error: "", movements: [], movementSaving: false, movementError: "",
  };
  render();
  ensureSuppliersLoaded();
}

async function openProductModal(productId) {
  try {
    const response = await api(`/api/products/${productId}`);
    const product = await response.json();
    state.modal = {
      open: true, mode: "edit", product,
      saving: false, error: "", movements: [], movementSaving: false, movementError: "",
    };
    render();
    ensureSuppliersLoaded();
    loadMovements(productId);
  } catch (error) {
    state.warehouse.error = error.message;
    render();
  }
}

async function loadMovements(productId) {
  try {
    const response = await api(`/api/products/${productId}/movements`);
    const movements = await response.json();
    if (state.modal.open && state.modal.product?.id === productId) {
      state.modal.movements = movements;
      render();
    }
  } catch (_) {
    // Non-fatal: the card still works without movement history.
  }
}

function closeModal() {
  state.modal = {
    open: false, mode: "edit", product: null,
    saving: false, error: "", movements: [], movementSaving: false, movementError: "",
  };
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
              <span>Поставщик (текст)</span>
              <input id="pf-supplier" value="${escapeHtml(p.supplier)}" />
            </label>
            <label class="form-label">
              <span>Поставщик (справочник)</span>
              <select id="pf-supplier-id">
                <option value="">— не выбран —</option>
                ${(state.suppliers.rows || [])
                  .map((s) => `<option value="${s.id}" ${p.supplier_id === s.id ? "selected" : ""}>${escapeHtml(s.name)}</option>`)
                  .join("")}
              </select>
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

        ${!isCreate && canRisk ? modalMovementsTemplate(p) : ""}
      </div>
    </div>
  `;
}

function modalMovementsTemplate(p) {
  const movements = state.modal.movements || [];
  return `
    <section class="movements-section">
      <div class="movements-head">
        <h4>Движения склада</h4>
        <span>Текущий остаток: <strong>${escapeHtml(p.stock)} шт.</strong></span>
      </div>

      ${state.modal.movementError ? `<div class="error-box" style="margin-bottom:10px">${escapeHtml(state.modal.movementError)}</div>` : ""}

      <form id="movement-form" class="movement-form">
        <select id="mv-type">
          ${MOVEMENT_TYPES.map((m) => `<option value="${m.code}">${escapeHtml(m.label)}</option>`).join("")}
        </select>
        <input id="mv-qty" type="number" placeholder="Кол-во" value="1" />
        <input id="mv-note" type="text" placeholder="Комментарий (необязательно)" />
        ${button(state.modal.movementSaving ? "..." : "Провести", "button-secondary", `type="submit" ${state.modal.movementSaving ? "disabled" : ""}`)}
      </form>
      <small class="movements-hint">Для «Корректировки» можно указать отрицательное количество.</small>

      <div class="movements-list">
        ${
          movements.length
            ? `
            <table class="data-table movements-table">
              <thead>
                <tr><th>Когда</th><th>Тип</th><th>Δ</th><th>Остаток</th><th>Кто</th><th>Комментарий</th></tr>
              </thead>
              <tbody>
                ${movements
                  .map(
                    (m) => `
                    <tr>
                      <td>${escapeHtml(formatDateTime(m.created_at))}</td>
                      <td>${escapeHtml(MOVEMENT_LABELS[m.movement_type] || m.movement_type)}</td>
                      <td class="${m.quantity >= 0 ? "mv-plus" : "mv-minus"}">${m.quantity >= 0 ? "+" : ""}${escapeHtml(m.quantity)}</td>
                      <td>${escapeHtml(m.stock_after)}</td>
                      <td>${escapeHtml(m.created_by_name || "—")}</td>
                      <td>${escapeHtml(m.note || "")}</td>
                    </tr>
                  `,
                  )
                  .join("")}
              </tbody>
            </table>
          `
            : `<div class="empty-state" style="min-height:54px">Движений пока нет.</div>`
        }
      </div>
    </section>
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
  document.getElementById("movement-form")?.addEventListener("submit", submitMovement);

  const onKey = (e) => {
    if (e.key === "Escape") {
      closeModal();
      document.removeEventListener("keydown", onKey);
    }
  };
  document.addEventListener("keydown", onKey);
}

async function submitMovement(event) {
  event.preventDefault();
  const productId = state.modal.product.id;
  // Read before render() rebuilds the DOM.
  const body = {
    movement_type: document.getElementById("mv-type").value,
    quantity: Number(document.getElementById("mv-qty").value),
    note: document.getElementById("mv-note").value.trim(),
  };

  if (!Number.isInteger(body.quantity) || body.quantity === 0) {
    state.modal.movementError = "Количество должно быть целым числом, не равным нулю.";
    render();
    return;
  }

  state.modal.movementSaving = true;
  state.modal.movementError = "";
  render();

  try {
    await api(`/api/products/${productId}/movements`, { method: "POST", body: JSON.stringify(body) });
    // Refresh product (stock changed) and movement history.
    const fresh = await (await api(`/api/products/${productId}`)).json();
    state.modal.product = fresh;
    state.modal.movementSaving = false;
    render();
    await loadMovements(productId);
    // Keep warehouse/risks tables and dashboard in sync.
    const idx = state.warehouse.rows.findIndex((r) => r.id === productId);
    if (idx !== -1) state.warehouse.rows[idx] = fresh;
    refreshDashboard();
  } catch (error) {
    state.modal.movementSaving = false;
    state.modal.movementError = error.message;
    render();
  }
}

function readProductForm() {
  const get = (id) => document.getElementById(id);
  return {
    sku: get("pf-sku").value.trim(),
    name: get("pf-name").value.trim(),
    category: get("pf-category").value.trim() || "Без категории",
    supplier: get("pf-supplier").value.trim(),
    supplier_id: get("pf-supplier-id").value ? Number(get("pf-supplier-id").value) : null,
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

