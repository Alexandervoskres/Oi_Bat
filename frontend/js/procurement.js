// Part of СкладAI frontend. Loaded as an ordered classic script (see index.html).
// Shares globals (state, render, helpers) defined in core.js.

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

