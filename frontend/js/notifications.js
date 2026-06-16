// Part of СкладAI frontend. Loaded as an ordered classic script (see index.html).
// Shares globals (state, render, helpers) defined in core.js.

// ─── Notifications center ─────────────────────────────────────────────────────

const NOTIFICATION_TYPE_LABELS = {
  low_stock: "Закупка",
  dead_stock: "Залежалость",
  margin_low: "Маржа",
  import_warning: "Импорт",
  supplier_overdue: "Поставщик",
};

function notificationsTemplate() {
  const model = state.notifications;
  const canScan = ["admin", "manager"].includes(state.user.role);
  const items = model.onlyUnread ? model.items.filter((n) => !n.is_read) : model.items;

  return `
    <section class="screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">центр оповещений</span>
          <h2>Уведомления ${model.unread ? `<span class="title-badge">${model.unread}</span>` : ""}</h2>
        </div>
        <div class="toolbar">
          <label class="flag-check" style="white-space:nowrap">
            <input type="checkbox" id="notif-only-unread" ${model.onlyUnread ? "checked" : ""} />
            <span>Только непрочитанные</span>
          </label>
          ${model.unread ? button("Прочитать все", "button-secondary", 'type="button" id="notif-read-all"') : ""}
          ${canScan ? button("Проверить склад", "", 'type="button" id="notif-scan"') : ""}
        </div>
      </header>

      ${model.error ? `<div class="error-box" style="margin-bottom:14px">${escapeHtml(model.error)}</div>` : ""}

      <section class="panel">
        ${
          model.loading
            ? `<div class="empty-state">Загружаю...</div>`
            : items.length
              ? `<div class="notif-list">
                  ${items
                    .map(
                      (n) => `
                      <article class="notif-row ${n.is_read ? "notif-read" : ""}" data-id="${n.id}">
                        <span class="notif-dot status-${escapeHtml(n.severity)}"></span>
                        <div class="notif-body">
                          <div class="notif-head">
                            <strong>${escapeHtml(n.title)}</strong>
                            <span class="notif-type">${escapeHtml(NOTIFICATION_TYPE_LABELS[n.type] || n.type)}</span>
                          </div>
                          <p>${escapeHtml(n.message)}</p>
                          <small>${escapeHtml(formatDateTime(n.created_at))}</small>
                        </div>
                        ${n.is_read ? "" : `<button class="btn-mini notif-read-btn" data-id="${n.id}">Прочитано</button>`}
                      </article>
                    `,
                    )
                    .join("")}
                </div>`
              : `<div class="empty-state">${model.onlyUnread ? "Непрочитанных уведомлений нет." : "Уведомлений нет. Нажмите «Проверить склад»."}</div>`
        }
      </section>
    </section>
  `;
}

function bindNotifications() {
  document.getElementById("notif-scan")?.addEventListener("click", scanNotifications);
  document.getElementById("notif-read-all")?.addEventListener("click", markAllNotificationsRead);
  document.getElementById("notif-only-unread")?.addEventListener("change", (e) => {
    state.notifications.onlyUnread = e.target.checked;
    render();
  });
  document.querySelectorAll(".notif-read-btn").forEach((btn) => {
    btn.addEventListener("click", () => markNotificationRead(Number(btn.dataset.id)));
  });
}

async function loadNotifications() {
  state.notifications.loading = true;
  state.notifications.error = "";
  render();
  try {
    const response = await api("/api/notifications");
    const data = await response.json();
    state.notifications.items = data.items;
    state.notifications.unread = data.unread;
  } catch (error) {
    state.notifications.error = error.message;
  } finally {
    state.notifications.loading = false;
    render();
  }
}

async function scanNotifications() {
  state.notifications.loading = true;
  state.notifications.error = "";
  render();
  try {
    const response = await api("/api/notifications/scan", { method: "POST" });
    const data = await response.json();
    state.notifications.items = data.items;
    state.notifications.unread = data.unread;
  } catch (error) {
    state.notifications.error = error.message;
  } finally {
    state.notifications.loading = false;
    render();
  }
}

async function markNotificationRead(id) {
  try {
    await api(`/api/notifications/${id}/read`, { method: "POST" });
    const note = state.notifications.items.find((n) => n.id === id);
    if (note && !note.is_read) {
      note.is_read = true;
      state.notifications.unread = Math.max(0, state.notifications.unread - 1);
    }
    render();
  } catch (error) {
    state.notifications.error = error.message;
    render();
  }
}

async function markAllNotificationsRead() {
  try {
    await api("/api/notifications/read-all", { method: "POST" });
    state.notifications.items.forEach((n) => (n.is_read = true));
    state.notifications.unread = 0;
    render();
  } catch (error) {
    state.notifications.error = error.message;
    render();
  }
}
