// Part of СкладAI frontend. Loaded as an ordered classic script (see index.html).
// Shares globals (state, render, helpers) defined in core.js.

// ─── Purchase orders ──────────────────────────────────────────────────────────

const ORDER_STATUS = {
  draft: { label: "Черновик", cls: "normal" },
  sent: { label: "Отправлен", cls: "warning" },
  received: { label: "Получен", cls: "positive" },
  cancelled: { label: "Отменён", cls: "critical" },
};

function orderStatusActions(order) {
  const canEdit = ["admin", "manager"].includes(state.user.role);
  if (!canEdit) return "";
  const actions = [];
  if (order.status === "draft") {
    actions.push(`<button class="btn-mini btn-order-status" data-id="${order.id}" data-status="sent">Отправить</button>`);
    actions.push(`<button class="btn-mini btn-order-status" data-id="${order.id}" data-status="cancelled">Отменить</button>`);
  } else if (order.status === "sent") {
    actions.push(`<button class="btn-mini btn-order-status" data-id="${order.id}" data-status="received">Получить (приход)</button>`);
    actions.push(`<button class="btn-mini btn-order-status" data-id="${order.id}" data-status="cancelled">Отменить</button>`);
  }
  if (state.user.role === "admin") {
    actions.push(`<button class="btn-mini btn-order-delete" data-id="${order.id}">Удалить</button>`);
  }
  return actions.join("");
}

function ordersTemplate() {
  const model = state.orders;
  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">снабжение</span>
          <h2>Заказы поставщикам</h2>
        </div>
        ${button("Обновить", "button-secondary", 'type="button" id="orders-refresh"')}
      </header>

      ${model.error ? `<div class="error-box" style="margin-bottom:14px">${escapeHtml(model.error)}</div>` : ""}
      ${model.message ? `<div class="notice-box" style="margin-bottom:14px">${escapeHtml(model.message)}</div>` : ""}

      <section class="panel">
        ${
          model.loading
            ? `<div class="empty-state">Загружаю заказы...</div>`
            : model.rows.length
              ? `
              <table class="data-table orders-table">
                <thead>
                  <tr><th>№</th><th>Поставщик</th><th>Позиций</th><th>Сумма</th><th>Статус</th><th>Создан</th><th>Действия</th></tr>
                </thead>
                <tbody>
                  ${model.rows
                    .map((order) => {
                      const st = ORDER_STATUS[order.status] || { label: order.status, cls: "normal" };
                      const expanded = model.expandedId === order.id;
                      return `
                      <tr class="order-row" data-id="${order.id}">
                        <td><strong>#${order.id}</strong></td>
                        <td>${escapeHtml(order.supplier_name || "Без поставщика")}</td>
                        <td>${escapeHtml(order.item_count)}</td>
                        <td>${formatMoney(order.total_amount)}</td>
                        <td>${statusPill(st.label, st.cls)}</td>
                        <td>${escapeHtml(formatDateTime(order.created_at))}<span>${escapeHtml(order.created_by_name || "")}</span></td>
                        <td class="row-actions">${orderStatusActions(order)}</td>
                      </tr>
                      ${
                        expanded
                          ? `<tr class="order-detail-row"><td colspan="7">
                              <table class="order-items">
                                <thead><tr><th>Артикул</th><th>Товар</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr></thead>
                                <tbody>
                                  ${order.items
                                    .map(
                                      (i) => `<tr>
                                        <td>${escapeHtml(i.sku)}</td>
                                        <td>${escapeHtml(i.name)}</td>
                                        <td>${escapeHtml(i.quantity)} шт.</td>
                                        <td>${formatMoney(i.purchase_price)}</td>
                                        <td>${formatMoney(i.line_total)}</td>
                                      </tr>`,
                                    )
                                    .join("")}
                                </tbody>
                              </table>
                              ${order.note ? `<div class="order-note">Комментарий: ${escapeHtml(order.note)}</div>` : ""}
                              <div style="margin-top:10px">
                                ${button("Скачать заказ (CSV)", "button-secondary button-sm btn-order-csv", `type="button" data-id="${order.id}"`)}
                              </div>
                            </td></tr>`
                          : ""
                      }
                    `;
                    })
                    .join("")}
                </tbody>
              </table>
            `
              : `<div class="empty-state">Заказов пока нет. Сформируйте заказ на экране «Закупки».</div>`
        }
      </section>
    </section>
  `;
}

function bindOrders() {
  document.getElementById("orders-refresh")?.addEventListener("click", loadOrders);
  document.querySelectorAll(".order-row").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest("button")) return; // don't toggle when clicking an action
      const id = Number(row.dataset.id);
      state.orders.expandedId = state.orders.expandedId === id ? null : id;
      render();
    });
  });
  document.querySelectorAll(".btn-order-status").forEach((btn) => {
    btn.addEventListener("click", () => updateOrderStatus(Number(btn.dataset.id), btn.dataset.status));
  });
  document.querySelectorAll(".btn-order-delete").forEach((btn) => {
    btn.addEventListener("click", () => deleteOrder(Number(btn.dataset.id)));
  });
  document.querySelectorAll(".btn-order-csv").forEach((btn) => {
    btn.addEventListener("click", () => exportOrderCsv(Number(btn.dataset.id)));
  });
}

function exportOrderCsv(id) {
  const order = state.orders.rows.find((o) => o.id === id);
  if (!order) return;
  const headers = ["Артикул", "Товар", "Кол-во", "Цена закупки", "Сумма"];
  const lines = [
    `Заказ #${order.id};Поставщик: ${order.supplier_name || "—"};Статус: ${order.status}`,
    headers.join(";"),
  ];
  for (const i of order.items) {
    lines.push([i.sku, i.name, i.quantity, i.purchase_price, i.line_total.toFixed(2)]
      .map(csvCell).join(";"));
  }
  lines.push(`;;;Итого:;${order.total_amount.toFixed(2)}`);
  const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `zakaz-${order.id}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function loadOrders() {
  state.orders.loading = true;
  state.orders.error = "";
  render();
  try {
    const response = await api("/api/orders");
    state.orders.rows = await response.json();
  } catch (error) {
    state.orders.error = error.message;
  } finally {
    state.orders.loading = false;
    render();
  }
}

async function updateOrderStatus(id, status) {
  if (status === "received" && !window.confirm("Отметить заказ полученным? Будет создан приход на склад.")) return;
  if (status === "cancelled" && !window.confirm("Отменить заказ?")) return;
  state.orders.message = "";
  try {
    const response = await api(`/api/orders/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
    const updated = await response.json();
    const idx = state.orders.rows.findIndex((o) => o.id === id);
    if (idx !== -1) state.orders.rows[idx] = updated;
    if (status === "received") {
      state.orders.message = `Заказ #${id} получен — остатки пополнены.`;
      refreshDashboard();
    }
    render();
  } catch (error) {
    state.orders.error = error.message;
    render();
  }
}

async function deleteOrder(id) {
  if (!window.confirm(`Удалить заказ #${id}?`)) return;
  try {
    await api(`/api/orders/${id}`, { method: "DELETE" });
    state.orders.rows = state.orders.rows.filter((o) => o.id !== id);
    render();
  } catch (error) {
    state.orders.error = error.message;
    render();
  }
}
