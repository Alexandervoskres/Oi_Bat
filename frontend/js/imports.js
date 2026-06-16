// Part of СкладAI frontend. Loaded as an ordered classic script (see index.html).
// Shares globals (state, render, helpers) defined in core.js.

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

