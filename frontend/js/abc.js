// Part of СкладAI frontend. Loaded as an ordered classic script (see index.html).
// Shares globals (state, render, helpers) defined in core.js.

// ─── ABC/XYZ analysis ─────────────────────────────────────────────────────────

function abcBadge(letter, kind) {
  if (!letter) return `<span class="abc-badge abc-na">—</span>`;
  return `<span class="abc-badge abc-${kind}-${letter}">${escapeHtml(letter)}</span>`;
}

function abcTemplate() {
  const model = state.abc;
  const data = model.data;
  const matrix = data ? data.matrix : {};
  const abcRows = ["A", "B", "C"];
  const xyzCols = ["X", "Y", "Z"];

  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">классификация ассортимента</span>
          <h2>ABC/XYZ-анализ</h2>
        </div>
        ${button("Обновить", "button-secondary", 'type="button" id="abc-refresh"')}
      </header>

      ${model.error ? `<div class="error-box" style="margin-bottom:14px">${escapeHtml(model.error)}</div>` : ""}

      ${
        model.loading
          ? `<div class="panel"><div class="empty-state">Считаю классификацию...</div></div>`
          : !data || !data.rows.length
            ? `<div class="panel"><div class="empty-state">Нет товаров для анализа. Загрузите данные.</div></div>`
            : `
            <div class="abc-top">
              <section class="panel">
                <div class="panel-title"><h3>Матрица ABC × XYZ</h3><span>товаров: ${escapeHtml(data.totals.products)}</span></div>
                <table class="abc-matrix">
                  <thead>
                    <tr><th></th>${xyzCols.map((c) => `<th>${c}</th>`).join("")}</tr>
                  </thead>
                  <tbody>
                    ${abcRows
                      .map(
                        (r) => `
                        <tr>
                          <th>${r}</th>
                          ${xyzCols
                            .map((c) => {
                              const n = matrix[`${r}${c}`] || 0;
                              return `<td class="abc-cell ${n ? `abc-cell-${r}${c}` : "abc-cell-empty"}">${n}</td>`;
                            })
                            .join("")}
                        </tr>
                      `,
                      )
                      .join("")}
                  </tbody>
                </table>
                <div class="abc-legend">
                  <span><b>ABC</b> — вклад в выручку (A≈80%, B≈15%, C≈5%)</span>
                  <span><b>XYZ</b> — стабильность спроса (X стабильно, Z скачет)</span>
                </div>
              </section>
            </div>

            <section class="panel">
              <div class="panel-title"><h3>Товары</h3><span>выручка/мес: ${formatMoney(data.totals.revenue)}</span></div>
              <table class="data-table abc-table">
                <thead>
                  <tr><th>Товар</th><th>Выручка/мес</th><th>Доля</th><th>ABC</th><th>XYZ</th><th>CV</th><th>Рекомендация</th></tr>
                </thead>
                <tbody>
                  ${data.rows
                    .map(
                      (row) => `
                      <tr>
                        <td><strong>${escapeHtml(row.name)}</strong><span>${escapeHtml(row.sku)} · ${escapeHtml(row.category)}</span></td>
                        <td>${formatMoney(row.revenue)}</td>
                        <td>${escapeHtml(row.revenue_share)}%</td>
                        <td>${abcBadge(row.abc, "abc")}</td>
                        <td>${abcBadge(row.xyz, "xyz")}</td>
                        <td>${row.cv === null ? "—" : escapeHtml(row.cv)}</td>
                        <td class="abc-reco">${escapeHtml(row.recommendation)}</td>
                      </tr>
                    `,
                    )
                    .join("")}
                </tbody>
              </table>
            </section>
          `
      }
    </section>
  `;
}

function bindAbc() {
  document.getElementById("abc-refresh")?.addEventListener("click", loadAbc);
}

async function loadAbc() {
  state.abc.loading = true;
  state.abc.error = "";
  render();
  try {
    const response = await api("/api/analytics/abc-xyz");
    state.abc.data = await response.json();
  } catch (error) {
    state.abc.error = error.message;
  } finally {
    state.abc.loading = false;
    render();
  }
}
