/**
 * AI Academic Advisor Frontend Application
 * Handles chat communication, profile management, and source citations.
 */

let conversationId = localStorage.getItem("conversation_id") || "";

const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const btnNewChat = document.getElementById("btn-new-chat");
const btnClearChat = document.getElementById("btn-clear-chat");
const profileForm = document.getElementById("profile-form");
const statusDot = document.querySelector(".status-dot");
const statusText = document.getElementById("status-text");

// Auto-expand textarea
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
});

// Submit on Enter (without Shift)
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    chatForm.dispatchEvent(new Event("submit"));
  }
});

// Quick question buttons
document.querySelectorAll(".quick-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const q = btn.getAttribute("data-query");
    if (q) {
      chatInput.value = q;
      chatForm.dispatchEvent(new Event("submit"));
    }
  });
});

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
      const data = await res.json();
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

// Append message bubble
function appendMessage(role, text, sources = []) {
  const welcomeCard = document.querySelector(".welcome-card");
  if (welcomeCard) {
    welcomeCard.remove();
  }

  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "🧑" : "🤖";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  // Add source citations if present
  if (sources && sources.length > 0) {
    const sourcesCard = document.createElement("div");
    sourcesCard.className = "sources-card";

    const header = document.createElement("div");
    header.className = "sources-header";
    header.innerHTML = "<span>📚 Nguồn tài liệu tham khảo:</span>";
    sourcesCard.appendChild(header);

    sources.forEach((s) => {
      const item = document.createElement("div");
      item.className = "source-item";
      let details = `• <strong>${s.source_file}</strong>`;
      if (s.section) details += ` | ${s.section}`;
      if (s.subsection) details += ` (${s.subsection})`;
      item.innerHTML = details;
      sourcesCard.appendChild(item);
    });

    bubble.appendChild(sourcesCard);
  }

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Append loading indicator
function showLoading() {
  const row = document.createElement("div");
  row.className = "message-row assistant";
  row.id = "loading-indicator";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "🤖";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = `
    <div class="typing-dots">
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
    </div>
  `;

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideLoading() {
  const loading = document.getElementById("loading-indicator");
  if (loading) {
    loading.remove();
  }
}

// Submit chat message
chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;

  appendMessage("user", message);
  chatInput.value = "";
  chatInput.style.height = "auto";

  showLoading();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message,
        conversation_id: conversationId || undefined,
      }),
    });

    hideLoading();

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      const errMsg = (errData.error && errData.error.message) || "Không thể nhận phản hồi từ máy chủ.";
      appendMessage("assistant", `⚠️ ${errMsg}`);
      return;
    }

    const data = await response.json();
    if (data.conversation_id) {
      conversationId = data.conversation_id;
      localStorage.setItem("conversation_id", conversationId);
    }

    appendMessage("assistant", data.answer, data.sources);
  } catch (err) {
    hideLoading();
    appendMessage("assistant", "⚠️ Không thể kết nối đến máy chủ. Vui lòng kiểm tra lại dịch vụ backend.");
  }
});

// Initial startup calls
loadProfile();
checkHealth();
