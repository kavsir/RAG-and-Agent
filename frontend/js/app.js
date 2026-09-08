/**
 * AI Academic Advisor Frontend Application
 * UX1: Real-time HTTP SSE Streaming + Visible Agent Progress
 * Preserves 100% vanilla JS, zero external frameworks, complete profile & session support.
 */

let conversationId = localStorage.getItem("conversation_id") || "";
let activeAbortController = null;
let isStreaming = false;

const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const btnSend = document.getElementById("btn-send");
const btnNewChat = document.getElementById("btn-new-chat");
const btnClearChat = document.getElementById("btn-clear-chat");
const profileForm = document.getElementById("profile-form");
const statusDot = document.querySelector(".status-dot");
const statusText = document.getElementById("status-text");

const originalSendBtnHtml = btnSend ? btnSend.innerHTML : "";

// Auto-expand textarea
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
});

// Submit on Enter (without Shift)
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (isStreaming) {
      stopStreaming();
    } else {
      chatForm.dispatchEvent(new Event("submit"));
    }
  }
});

// Send / Stop button click
if (btnSend) {
  btnSend.addEventListener("click", (e) => {
    if (isStreaming) {
      e.preventDefault();
      stopStreaming();
    }
  });
}

// Quick question buttons
document.querySelectorAll(".quick-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (isStreaming) return;
    const q = btn.getAttribute("data-query");
    if (q) {
      chatInput.value = q;
      chatForm.dispatchEvent(new Event("submit"));
    }
  });
});

// Auto-scroll helper (only if near bottom)
function isNearBottom(el, threshold = 80) {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
}

function autoScrollIfNeeded() {
  if (isNearBottom(chatMessages)) {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
}

// Update Send / Stop button state
function setStreamingState(streaming) {
  isStreaming = streaming;
  if (!btnSend) return;

  if (streaming) {
    btnSend.classList.add("btn-stop");
    btnSend.title = "Dừng xử lý (Stop)";
    btnSend.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <rect x="4" y="4" width="16" height="16" rx="2"></rect>
      </svg>
    `;
    chatInput.placeholder = "Agent đang xử lý... Nhấn Dừng để hủy.";
  } else {
    btnSend.classList.remove("btn-stop");
    btnSend.title = "Gửi tin nhắn";
    btnSend.innerHTML = originalSendBtnHtml;
    chatInput.placeholder = "Hỏi về môn học, giảng viên, tín chỉ, quy chế đào tạo...";
    activeAbortController = null;
  }
}

function stopStreaming() {
  if (activeAbortController) {
    activeAbortController.abort();
    activeAbortController = null;
  }
  setStreamingState(false);
}

// Load profile on start
async function loadProfile() {
  try {
    const res = await fetch("/api/profile");
    if (res.ok) {
      const data = await res.json();
      document.getElementById("prof-name").value = data.name || "";
      document.getElementById("prof-major").value = data.major || "";
      document.getElementById("prof-cohort").value = data.cohort || "";
      document.getElementById("prof-email").value = data.email || "";
    }
  } catch (err) {
    console.error("Không thể tải hồ sơ:", err);
  }
}

// Save profile
profileForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    name: document.getElementById("prof-name").value.trim(),
    major: document.getElementById("prof-major").value.trim(),
    cohort: document.getElementById("prof-cohort").value.trim(),
    email: document.getElementById("prof-email").value.trim(),
  };

  try {
    const res = await fetch("/api/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      alert("✅ Đã cập nhật hồ sơ sinh viên!");
    }
  } catch (err) {
    alert("❌ Lỗi khi lưu hồ sơ.");
  }
});

// Check health
async function checkHealth() {
  try {
    const res = await fetch("/health");
    if (res.ok) {
      statusText.textContent = "Hệ thống sẵn sàng";
      statusDot.style.backgroundColor = "#22c55e";
    } else {
      statusText.textContent = "Hệ thống gián đoạn";
      statusDot.style.backgroundColor = "#f59e0b";
    }
  } catch (err) {
    statusText.textContent = "Không có kết nối backend";
    statusDot.style.backgroundColor = "#ef4444";
  }
}

// Clear chat
async function resetConversation() {
  if (isStreaming) {
    stopStreaming();
  }
  try {
    await fetch("/api/conversations/clear", { method: "POST" });
    conversationId = "";
    localStorage.removeItem("conversation_id");
    chatMessages.innerHTML = `
      <div class="welcome-card">
        <div class="welcome-icon">👋</div>
        <h3>Cuộc trò chuyện mới</h3>
        <p>Bộ nhớ đệm đã được làm mới. Hãy đặt câu hỏi về môn học, giảng viên, tín chỉ, hoặc quy chế.</p>
      </div>
    `;
  } catch (err) {
    console.error("Lỗi khi reset cuộc trò chuyện:", err);
  }
}

btnNewChat.addEventListener("click", resetConversation);
btnClearChat.addEventListener("click", resetConversation);

// Append user message bubble
function appendUserMessage(text) {
  const welcomeCard = document.querySelector(".welcome-card");
  if (welcomeCard) welcomeCard.remove();

  const row = document.createElement("div");
  row.className = "message-row user";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "🧑";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Create Assistant Streaming Message Container
function createAssistantStreamingRow() {
  const welcomeCard = document.querySelector(".welcome-card");
  if (welcomeCard) welcomeCard.remove();

  const row = document.createElement("div");
  row.className = "message-row assistant";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "🤖";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  // Thinking card component
  const thinkingCard = document.createElement("div");
  thinkingCard.className = "thinking-card";

  const thinkingHeader = document.createElement("div");
  thinkingHeader.className = "thinking-header";

  const titleGroup = document.createElement("div");
  titleGroup.className = "thinking-title-group";

  const sparkle = document.createElement("span");
  sparkle.className = "thinking-sparkle";
  sparkle.textContent = "✦";

  const titleText = document.createElement("span");
  titleText.className = "thinking-title-text";
  titleText.textContent = "Đang suy nghĩ...";

  titleGroup.appendChild(sparkle);
  titleGroup.appendChild(titleText);

  const timerEl = document.createElement("span");
  timerEl.className = "thinking-timer";
  timerEl.textContent = "0.0s";

  const toggleBtn = document.createElement("button");
  toggleBtn.type = "button";
  toggleBtn.className = "thinking-toggle";
  toggleBtn.style.display = "none";
  toggleBtn.textContent = "Xem quá trình xử lý ▼";

  thinkingHeader.appendChild(titleGroup);
  thinkingHeader.appendChild(timerEl);
  thinkingHeader.appendChild(toggleBtn);

  const thinkingBody = document.createElement("div");
  thinkingBody.className = "thinking-body";

  const timeline = document.createElement("div");
  timeline.className = "thinking-timeline";
  thinkingBody.appendChild(timeline);

  thinkingCard.appendChild(thinkingHeader);
  thinkingCard.appendChild(thinkingBody);

  // Toggle button collapse/expand handler
  toggleBtn.addEventListener("click", () => {
    if (thinkingBody.style.display === "none") {
      thinkingBody.style.display = "block";
      toggleBtn.textContent = "Thu gọn ▲";
    } else {
      thinkingBody.style.display = "none";
      toggleBtn.textContent = "Xem quá trình xử lý ▼";
    }
  });

  // Answer content area
  const answerContent = document.createElement("div");
  answerContent.className = "answer-content";

  // Sources card (hidden initially)
  const sourcesCard = document.createElement("div");
  sourcesCard.className = "sources-card";
  sourcesCard.style.display = "none";

  // Clarification actions area (hidden initially)
  const clarificationActions = document.createElement("div");
  clarificationActions.className = "clarification-actions";
  clarificationActions.style.display = "none";

  bubble.appendChild(thinkingCard);
  bubble.appendChild(answerContent);
  bubble.appendChild(sourcesCard);
  bubble.appendChild(clarificationActions);

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  autoScrollIfNeeded();

  // Timer logic
  const startTime = performance.now();
  let timerInterval = setInterval(() => {
    const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
    timerEl.textContent = `${elapsed}s`;
  }, 100);

  return {
    row,
    bubble,
    thinkingCard,
    titleText,
    sparkle,
    timerEl,
    toggleBtn,
    thinkingBody,
    timeline,
    answerContent,
    sourcesCard,
    clarificationActions,
    startTime,
    stopTimer: () => {
      if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
      }
    },
  };
}

// Structured Phase Labels
const PHASE_COMPLETED_LABELS = {
  UNDERSTAND: "Đã hiểu yêu cầu",
  OBSERVE: "Đã kiểm tra ngữ cảnh và dữ liệu",
  PLAN: "Đã xác định cách xử lý phù hợp",
  ACT: "Đã tra cứu dữ liệu học vụ",
  VERIFY: "Đã xác minh bằng chứng chính thống",
  PREPARE_ANSWER: "Đã chuẩn bị xong câu trả lời",
};

// Main SSE Stream Processor
async function sendStreamingMessage(message) {
  appendUserMessage(message);
  setStreamingState(true);

  activeAbortController = new AbortController();
  const ctx = createAssistantStreamingRow();

  // Active typing cursor
  let cursor = null;
  function ensureCursor() {
    if (!cursor) {
      cursor = document.createElement("span");
      cursor.className = "typing-cursor";
      ctx.answerContent.appendChild(cursor);
    }
  }
  function removeCursor() {
    if (cursor) {
      cursor.remove();
      cursor = null;
    }
  }

  // Phase tracker
  const phaseElements = new Map();
  let currentActivePhase = null;

  function updatePhaseUI(phase, label) {
    // Mark previous phase as done
    if (currentActivePhase && currentActivePhase !== phase) {
      const prevEl = phaseElements.get(currentActivePhase);
      if (prevEl) {
        prevEl.className = "timeline-item done";
        const icon = prevEl.querySelector(".step-icon");
        if (icon) icon.textContent = "✓";
        const textSpan = prevEl.querySelector(".step-text");
        if (textSpan && PHASE_COMPLETED_LABELS[currentActivePhase]) {
          textSpan.textContent = PHASE_COMPLETED_LABELS[currentActivePhase];
        }
      }
    }

    currentActivePhase = phase;
    let itemEl = phaseElements.get(phase);
    if (!itemEl) {
      itemEl = document.createElement("div");
      itemEl.className = "timeline-item active";
      itemEl.innerHTML = `
        <span class="step-icon">◌</span>
        <span class="step-text">${label || phase}</span>
      `;
      ctx.timeline.appendChild(itemEl);
      phaseElements.set(phase, itemEl);
    } else {
      itemEl.className = "timeline-item active";
      const icon = itemEl.querySelector(".step-icon");
      if (icon) icon.textContent = "◌";
      const textSpan = itemEl.querySelector(".step-text");
      if (textSpan && label) textSpan.textContent = label;
    }

    ctx.titleText.textContent = label || "Đang xử lý...";
    autoScrollIfNeeded();
  }

  function completeThinkingCard() {
    ctx.stopTimer();
    const finalElapsed = ((performance.now() - ctx.startTime) / 1000).toFixed(1);
    ctx.timerEl.textContent = `${finalElapsed}s`;

    // Mark all items done
    phaseElements.forEach((el, p) => {
      el.className = "timeline-item done";
      const icon = el.querySelector(".step-icon");
      if (icon) icon.textContent = "✓";
      const textSpan = el.querySelector(".step-text");
      if (textSpan && PHASE_COMPLETED_LABELS[p]) {
        textSpan.textContent = PHASE_COMPLETED_LABELS[p];
      }
    });

    // Update thinking card title to collapsed state
    ctx.sparkle.textContent = "✓";
    ctx.sparkle.style.animation = "none";
    ctx.sparkle.style.color = "#16a34a";
    ctx.titleText.textContent = `Đã xử lý trong ${finalElapsed}s`;

    // Collapse timeline by default
    ctx.thinkingBody.style.display = "none";
    ctx.toggleBtn.style.display = "inline-flex";
    ctx.toggleBtn.textContent = "Xem quá trình xử lý ▼";
  }

  // Handle individual structured SSE event
  function handleStreamEvent(eventType, eventData) {
    if (!eventData) return;

    if (eventData.conversation_id) {
      conversationId = eventData.conversation_id;
      localStorage.setItem("conversation_id", conversationId);
    }

    switch (eventType) {
      case "meta":
        if (eventData.data && eventData.data.conversation_id) {
          conversationId = eventData.data.conversation_id;
          localStorage.setItem("conversation_id", conversationId);
        }
        break;

      case "phase":
        updatePhaseUI(eventData.phase, eventData.label);
        break;

      case "tool_status":
        updatePhaseUI("ACT", eventData.label);
        break;

      case "answer_start":
        completeThinkingCard();
        ensureCursor();
        break;

      case "answer_delta":
        ensureCursor();
        if (eventData.data && eventData.data.delta) {
          // Insert delta before cursor
          cursor.insertAdjacentText("beforebegin", eventData.data.delta);
          autoScrollIfNeeded();
        }
        break;

      case "sources":
        if (eventData.data && eventData.data.items && eventData.data.items.length > 0) {
          const sources = eventData.data.items;
          ctx.sourcesCard.innerHTML = `
            <div class="sources-header">
              <span>📚 Nguồn tài liệu tham khảo:</span>
            </div>
          `;
          sources.forEach((s) => {
            const item = document.createElement("div");
            item.className = "source-item";
            let details = `• <strong>${s.source_file || s.chunk_id}</strong>`;
            if (s.section) details += ` | ${s.section}`;
            if (s.subsection) details += ` (${s.subsection})`;
            item.innerHTML = details;
            ctx.sourcesCard.appendChild(item);
          });
          ctx.sourcesCard.style.display = "block";
          autoScrollIfNeeded();
        }
        break;

      case "clarification":
        completeThinkingCard();
        if (eventData.data) {
          const { question, options } = eventData.data;
          if (options && options.length > 0) {
            ctx.clarificationActions.innerHTML = "";
            options.forEach((opt) => {
              const chip = document.createElement("button");
              chip.type = "button";
              chip.className = "clarification-chip";
              chip.textContent = opt;
              chip.addEventListener("click", () => {
                chatInput.value = opt;
                chatForm.dispatchEvent(new Event("submit"));
              });
              ctx.clarificationActions.appendChild(chip);
            });
            ctx.clarificationActions.style.display = "flex";
            autoScrollIfNeeded();
          }
        }
        break;

      case "done":
        completeThinkingCard();
        removeCursor();
        setStreamingState(false);
        autoScrollIfNeeded();
        break;

      case "error":
        completeThinkingCard();
        removeCursor();
        const errMsg = (eventData.data && eventData.data.message) || "Đã xảy ra lỗi khi xử lý yêu cầu.";
        ctx.answerContent.innerHTML += `<div style="color: #ef4444; margin-top: 6px;">⚠️ ${errMsg}</div>`;
        setStreamingState(false);
        autoScrollIfNeeded();
        break;

      case "ping":
        // Heartbeat keep-alive
        break;

      default:
        break;
    }
  }

  // Parse SSE wire format
  function parseAndHandleSSE(rawMessage) {
    let eventType = "message";
    let dataStr = "";

    const lines = rawMessage.split(/\r?\n/);
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const dataPart = line.slice(5).trim();
        dataStr = dataStr ? dataStr + "\n" + dataPart : dataPart;
      }
    }

    if (!dataStr) return;
    try {
      const eventData = JSON.parse(dataStr);
      handleStreamEvent(eventType, eventData);
    } catch (err) {
      console.warn("Malformed SSE JSON payload:", dataStr, err);
    }
  }

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message,
        conversation_id: conversationId || undefined,
      }),
      signal: activeAbortController.signal,
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      const errMsg = (errData.error && errData.error.message) || "Không thể nhận phản hồi từ máy chủ.";
      completeThinkingCard();
      removeCursor();
      ctx.answerContent.innerHTML = `<div style="color: #ef4444;">⚠️ ${errMsg}</div>`;
      setStreamingState(false);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawMessage = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        if (rawMessage.trim()) {
          parseAndHandleSSE(rawMessage);
        }
        boundary = buffer.indexOf("\n\n");
      }
    }

    // Flush any remaining buffered characters
    buffer += decoder.decode();
    if (buffer.trim()) {
      parseAndHandleSSE(buffer);
    }

    completeThinkingCard();
    removeCursor();
    setStreamingState(false);
  } catch (err) {
    completeThinkingCard();
    removeCursor();
    setStreamingState(false);

    if (err.name === "AbortError") {
      // User pressed Stop
      if (!ctx.answerContent.textContent.trim()) {
        ctx.answerContent.innerHTML += `<div style="color: #64748b; font-style: italic; margin-top: 6px;">(Đã dừng phản hồi)</div>`;
      }
    } else {
      console.error("Stream connection error:", err);
      ctx.answerContent.innerHTML += `<div style="color: #ef4444; margin-top: 6px;">⚠️ Không thể kết nối đến máy chủ. Vui lòng kiểm tra lại dịch vụ backend.</div>`;
    }
  }
}

// Chat Form Submit Handler
chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (isStreaming) {
    stopStreaming();
    return;
  }

  const message = chatInput.value.trim();
  if (!message) return;

  chatInput.value = "";
  chatInput.style.height = "auto";

  await sendStreamingMessage(message);
});

// Initial startup calls
loadProfile();
checkHealth();
