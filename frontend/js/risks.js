// Part of СкладAI frontend. Loaded as an ordered classic script (see index.html).
// Shares globals (state, render, helpers) defined in core.js.

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

