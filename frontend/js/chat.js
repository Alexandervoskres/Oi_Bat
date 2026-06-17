// Part of СкладAI frontend. Loaded as an ordered classic script (see index.html).
// Shares globals (state, render, helpers) defined in core.js.

// ─── AI Chat ──────────────────────────────────────────────────────────────────

const CHAT_QUICK_QUESTIONS = [
  "Что заказать?",
  "Что не закупать?",
  "Что распродать?",
  "План на неделю",
  "Риски склада",
  "Заказ на 100 000 ₽",
];

function createChatMessage(role, text, extra = {}) {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    text,
    at: new Date().toISOString(),
    ...extra,
  };
}

function saveChatMessages() {
  state.chat.messages = state.chat.messages.slice(-80);
  writeSessionJson("skladai_chat_messages", state.chat.messages);
}

function chatActionTarget(action) {
  const text = String(action || "").toLowerCase();
  if (text.includes("csv")) return "csv";
  if (text.includes("закуп")) return "procurement";
  if (text.includes("риск") || text.includes("скид")) return "risks";
  if (text.includes("импорт")) return "imports";
  if (text.includes("карточ") || text.includes("товар")) return "warehouse";
  return "";
}

function chatAgentStatusTemplate(model) {
  const status = model.status;
  const activeAgent = model.statusLoading ? "Проверяю..." : "AI-ассистент";
  const ollama = status?.ollama;
  let stateText = "локальный режим";
  let stateClass = "local";
  if (ollama?.available) {
    stateText = `модель ${ollama.model || "подключена"}`;
    stateClass = "online";
  }
  return `
    <div class="chat-agent-status chat-agent-${stateClass}">
      <span class="chat-agent-dot"></span>
      <div>
        <strong>${escapeHtml(activeAgent)}</strong>
        <small>${escapeHtml(stateText)}</small>
      </div>
    </div>
  `;
}

function chatTemplate() {
  const model = state.chat;
  return `
    <section class="screen chat-screen">
      <header class="screen-header">
        <div>
          <span class="eyebrow">ассистент склада</span>
          <h2>AI-советник</h2>
        </div>
        <div class="chat-header-actions">
          ${chatAgentStatusTemplate(model)}
          ${model.messages.length ? button("Очистить", "button-secondary chat-clear", 'type="button" id="chat-clear"') : ""}
        </div>
      </header>

      <section class="panel chat-panel">
        <div class="chat-messages" id="chat-messages" aria-live="polite">
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
        <button class="chat-scroll-bottom" id="chat-scroll-bottom" type="button" hidden>Вниз</button>

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

function renderMarkdown(raw) {
  // Escape first, then apply a safe subset of markdown (bold, inline code,
  // paragraphs). Operating on already-escaped text means no user/agent content
  // can inject markup. Chat answers are rendered without automatic bullets or
  // numbering so model formatting never turns every line into a numbered block.
  const inline = (s) =>
    escapeHtml(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  const out = [];

  for (const line of String(raw ?? "").split("\n")) {
    const cleaned = line
      .replace(/^\s*(?:[•\-*]|\d+[.)])\s+/, "")
      .replace(/\s*\([^()]*\)/g, "")
      .trim();
    if (cleaned) out.push(`<div>${inline(cleaned)}</div>`);
  }
  return out.join("");
}

function chatBubbleContent(message) {
  const text =
    message.role === "assistant"
      ? renderMarkdown(message.text)
      : escapeHtml(message.text).replaceAll("\n", "<br>");
  const agent = message.role === "assistant" && message.agent ? `<div class="chat-agent-label">${escapeHtml(message.agent)}</div>` : "";
  const meta = `
    <div class="chat-meta">
      <span>${escapeHtml(formatChatTime(message.at))}</span>
      ${message.role === "user" ? `<span>${message.status === "error" ? "!" : message.status === "sending" ? "✓" : "✓✓"}</span>` : ""}
    </div>
  `;
  let products = "";
  if (message.role === "assistant" && message.used_products?.length) {
    products = `
      <div class="chat-products">
        ${message.used_products.slice(0, 8).map((p) => `<span>${escapeHtml(p)}</span>`).join("")}
      </div>
    `;
  }
  let actions = "";
  if (message.role === "assistant" && message.suggested_actions?.length) {
    actions = `
      <div class="chat-actions">
        ${message.suggested_actions
          .map((a) => `<button type="button" class="chat-action-tag" data-chat-action="${escapeHtml(a)}">${escapeHtml(a)}</button>`)
          .join("")}
      </div>
    `;
  }
  return `${agent}<div class="chat-text">${text}</div>${products}${actions}${meta}`;
}

function bindChat() {
  const form = document.getElementById("chat-form");
  if (!form) return;
  if (!state.chat.status && !state.chat.statusLoading) loadAiStatus();
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const input = document.getElementById("chat-input");
    sendChat(input.value);
  });

  document.getElementById("chat-clear")?.addEventListener("click", () => {
    state.chat.messages = [];
    state.chat.error = "";
    saveChatMessages();
    render();
  });

  document.querySelectorAll(".chat-chip").forEach((chip) => {
    chip.addEventListener("click", () => sendChat(chip.dataset.q));
  });

  const messagesEl = document.getElementById("chat-messages");
  const scrollButton = document.getElementById("chat-scroll-bottom");
  const scrollToBottom = () => {
    if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
  };
  if (messagesEl) {
    const updateScrollButton = () => {
      if (!scrollButton) return;
      const gap = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight;
      scrollButton.hidden = gap < 120;
    };
    messagesEl.addEventListener("scroll", updateScrollButton);
    scrollButton?.addEventListener("click", scrollToBottom);
    requestAnimationFrame(() => {
      scrollToBottom();
      updateScrollButton();
    });
  }

  const input = document.getElementById("chat-input");
  if (input) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
    input.addEventListener("input", () => {
      input.style.height = "auto";
      input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
    });
    if (!state.chat.loading) input.focus();
  }

  document.querySelectorAll("[data-chat-action]").forEach((actionButton) => {
    actionButton.addEventListener("click", () => handleChatAction(actionButton.dataset.chatAction));
  });
}

function buildChatHistory() {
  // Last few turns (oldest first) so the agent can resolve follow-up questions.
  // The current message is added by the caller, so exclude it here.
  return state.chat.messages
    .filter((m) => (m.role === "user" || m.role === "assistant") && m.text)
    .slice(-8)
    .map((m) => ({ role: m.role, content: m.text }));
}

function updateStreamingBubble(text) {
  const bubbles = document.querySelectorAll(".chat-msg-assistant .chat-text");
  const el = bubbles[bubbles.length - 1];
  if (el) el.textContent = text; // raw text while streaming; markdown applied on done
  const box = document.getElementById("chat-messages");
  if (box) box.scrollTop = box.scrollHeight;
}

async function sendChat(rawMessage) {
  const message = (rawMessage || "").trim();
  if (!message || state.chat.loading) return;

  const history = buildChatHistory();
  const userMessage = createChatMessage("user", message, { status: "sending" });
  state.chat.messages.push(userMessage);
  state.chat.loading = true;
  state.chat.error = "";
  saveChatMessages();
  render();

  let assistant = null;
  let acc = "";
  const ensureAssistant = () => {
    if (assistant) return;
    assistant = {
      ...createChatMessage("assistant", ""),
      role: "assistant",
      text: "",
      suggested_actions: [],
      used_products: [],
      agent: "",
      source: "",
    };
    state.chat.messages.push(assistant);
    state.chat.loading = false; // the streaming bubble now stands in for the spinner
    render();
  };

  try {
    const response = await fetch("/api/ai/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}),
      },
      body: JSON.stringify({ message, history }),
    });
    if (response.status === 401) {
      logout();
      return;
    }
    if (!response.ok || !response.body) throw new Error("Сервер недоступен");
    userMessage.status = "sent";

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let streamDone = false;
    while (!streamDone) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, sep).trim();
        buffer = buffer.slice(sep + 2);
        if (!raw.startsWith("data:")) continue;
        let evt;
        try {
          evt = JSON.parse(raw.slice(5).trim());
        } catch (_) {
          continue;
        }
        if (evt.type === "delta") {
          ensureAssistant();
          acc += evt.text || "";
          assistant.text = acc;
          updateStreamingBubble(acc);
        } else if (evt.type === "done") {
          ensureAssistant();
          assistant.text = evt.answer || acc;
          assistant.suggested_actions = evt.suggested_actions || [];
          assistant.used_products = evt.used_products || [];
          assistant.agent = evt.agent || "StoreAI";
          assistant.source = evt.source || "rule_based";
          streamDone = true;
        }
      }
    }
    if (!assistant) throw new Error("Пустой ответ");
  } catch (error) {
    userMessage.status = "error";
    if (!assistant) {
      state.chat.messages.push(
        createChatMessage("assistant", `Не смог получить ответ: ${error.message}`, { suggested_actions: ["Повторить вопрос"] }),
      );
    }
  } finally {
    state.chat.loading = false;
    saveChatMessages();
    render();
  }
}

async function handleChatAction(action) {
  if (String(action || "").toLowerCase().includes("повтор")) {
    const lastUserMessage = [...state.chat.messages].reverse().find((message) => message.role === "user");
    if (lastUserMessage) sendChat(lastUserMessage.text);
    return;
  }

  const target = chatActionTarget(action);
  if (!target) {
    sendChat(action);
    return;
  }

  if (target === "csv") {
    state.active = "procurement";
    render();
    if (!state.procurement.rows.length) await loadProcurement();
    exportProcurementCsv();
    return;
  }

  state.active = target;
  render();
  if (target === "procurement") await loadProcurement();
  if (target === "risks") await loadRisks();
  if (target === "imports" && !state.imports.rows.length) await loadImports();
  if (target === "warehouse" && !state.warehouse.rows.length) await loadProducts();
}

async function loadAiStatus() {
  state.chat.statusLoading = true;
  try {
    const response = await api("/api/ai/status");
    state.chat.status = await response.json();
  } catch (_) {
    state.chat.status = {
      active_agent: "StoreAI",
      fallback_agent: "StoreAI",
      ollama: { available: false, host: "", model: "" },
    };
  } finally {
    state.chat.statusLoading = false;
    if (state.active === "chat") render();
  }
}

