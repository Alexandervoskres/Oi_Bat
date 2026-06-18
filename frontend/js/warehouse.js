// Часть фронтенда СкладAI. Грузится как обычный <script> (порядок — в index.html).
// Общие глобалы (state, render, api, помощники) объявлены в core.js.
//
// Этот файл — ЭКРАН «СКЛАД»: таблица товаров, живой поиск, загрузка и удаление.
// Карточка товара (модальное окно) вынесена в product-modal.js.

// ─── Warehouse ────────────────────────────────────────────────────────────────

let warehouseSearchTimer = null;

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
          <div class="search-field telegram-search">
            <span class="search-icon" aria-hidden="true"></span>
            <input id="warehouse-search" placeholder="Поиск" autocomplete="off" value="${escapeHtml(model.search)}" />
            <button class="search-clear" id="warehouse-search-clear" type="button" aria-label="Очистить поиск" title="Очистить поиск" ${model.search ? "" : "hidden"}>&times;</button>
          </div>
          <select id="warehouse-status">
            ${statuses.map((item) => `<option value="${escapeHtml(item)}" ${model.status === item ? "selected" : ""}>${escapeHtml(item || "Все статусы")}</option>`).join("")}
          </select>
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
  const searchInput = document.getElementById("warehouse-search");
  const searchClear = document.getElementById("warehouse-search-clear");

  document.getElementById("warehouse-status").addEventListener("change", () => loadProducts());
  searchInput.addEventListener("input", () => {
    state.warehouse.search = searchInput.value;
    if (searchClear) searchClear.hidden = !searchInput.value;
    clearTimeout(warehouseSearchTimer);
    warehouseSearchTimer = setTimeout(() => loadProducts({ keepSearchFocus: true, silent: true }), 320);
  });
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      clearTimeout(warehouseSearchTimer);
      loadProducts({ keepSearchFocus: true });
    }
  });
  searchClear?.addEventListener("click", () => {
    clearTimeout(warehouseSearchTimer);
    searchInput.value = "";
    state.warehouse.search = "";
    searchClear.hidden = true;
    loadProducts({ keepSearchFocus: true });
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

async function loadProducts(options = {}) {
  const { keepSearchFocus = false, silent = false } = options;
  state.warehouse.search = document.getElementById("warehouse-search")?.value ?? state.warehouse.search;
  state.warehouse.status = document.getElementById("warehouse-status")?.value ?? state.warehouse.status;
  state.warehouse.loading = true;
  state.warehouse.error = "";
  if (!silent) render();

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
    if (keepSearchFocus) {
      const input = document.getElementById("warehouse-search");
      input?.focus();
      input?.setSelectionRange(input.value.length, input.value.length);
    }
  }
}

