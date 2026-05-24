import { API_BASE_URL } from "../config";

const getAuthToken = () => localStorage.getItem("token");

// ── Handle auth errors globally ───────────────────────────────────────────────
function handleAuthError() {
  localStorage.removeItem("token");
  window.location.href = "/sign-in";
}

// ── askGemini (non-streaming — used by standalone calls) ─────────────────────
export async function askGemini(prompt) {
  const token = getAuthToken();
  if (!token) throw new Error("Not authenticated");

  const res  = await fetch(`${API_BASE_URL}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ prompt }),
  });

  if (res.status === 401) { handleAuthError(); throw new Error("Unauthorized"); }

  const data = await res.json();
  if (!res.ok) throw new Error(data.details || data.error || "Generation failed");

  if (data.success) {
    let msg = `✅ **GNS3 project generated successfully!**\n\n`;
    if (data.log?.trim()) msg += `**Terminal output:**\n\`\`\`\n${data.log}\n\`\`\`\n\n`;
    msg += `📎 [Download ${data.filename}](${API_BASE_URL}${data.downloadUrl})\n\n_Import in GNS3 → File → Import portable project._`;
    return msg;
  }
  throw new Error(data.error || "Unknown error");
}

// ── askGeminiStream (streaming — used by NewPrompt and ChatPage) ──────────────
//
// FIX: Removed the double-context-building that was here before.
// Old behavior:
//   gemini.js built "Previous context: X | Current request: Y"
//   AND NewPrompt.jsx also wrapped with buildPrompt() system instructions
//   → Final prompt = system instructions wrapping a "Previous context" string
//   → Confusing, wastes tokens, degrades AI quality
//
// New behavior:
//   NewPrompt passes the full conversation history as `conversationHistory`
//   gemini.js just extracts the last user message and sends it with history as context
//   The Python pipeline uses the history for context — clean and correct
// ─────────────────────────────────────────────────────────────────────────────
export async function askGeminiStream(conversationHistory = [], imageDataList = [], onChunk = () => {}) {
  // Extract the last user message — this is what we send to the pipeline
  const lastUserMsg = [...conversationHistory]
    .reverse()
    .find(m => m.role === "user");

  const prompt = lastUserMsg?.content?.trim() || "";

  if (!prompt) {
    onChunk("⚠️ No prompt provided.");
    return;
  }

  const token = getAuthToken();
  if (!token) {
    onChunk("🔐 You are not logged in. Please sign in again.");
    return;
  }

  try {
    const res = await fetch(`${API_BASE_URL}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ prompt }),
    });

    if (res.status === 401) {
      handleAuthError();
      onChunk("🔐 Session expired. Redirecting to sign in...");
      return;
    }

    const data = await res.json();

    if (!res.ok) {
      onChunk(`❌ **Pipeline failed**\n\`\`\`\n${data.error || "Unknown error"}\n\`\`\``);
      return;
    }

    if (data.success) {
      let msg = `✅ **GNS3 project generated successfully!**\n\n`;
      if (data.log?.trim()) msg += `**Terminal output:**\n\`\`\`\n${data.log}\n\`\`\`\n\n`;
      msg += `📎 [Download ${data.filename}](${API_BASE_URL}${data.downloadUrl})\n\n_Import in GNS3 → File → Import portable project._`;
      onChunk(msg);
    } else {
      onChunk(`❌ **Error:** ${data.error || "Unknown error"}`);
    }
  } catch (err) {
    console.error("Generate error:", err);
    if (err.message?.includes("fetch") || err.name === "TypeError") {
      onChunk("❌ **Cannot reach the server.** Make sure the backend is running on port 3000.");
    } else {
      onChunk(`❌ **Network error:** ${err.message}`);
    }
  }
}

// ── uploadProjectFile ─────────────────────────────────────────────────────────
export async function uploadProjectFile(file) {
  const token = getAuthToken();
  if (!token) throw new Error("Not authenticated");

  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/api/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (res.status === 401) { handleAuthError(); throw new Error("Unauthorized"); }
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.error || "Upload failed");
  }
  return res.json();
}
