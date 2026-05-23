import { API_BASE_URL } from "../config";

const getAuthToken = () => localStorage.getItem('token');

export async function askGemini(prompt, images = []) {
  const token = getAuthToken();
  if (!token) throw new Error('Not authenticated');
  const response = await fetch(`${API_BASE_URL}/api/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ prompt }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.details || data.error || 'Generation failed');
  if (data.success) {
    let message = `✅ **GNS3 project generated successfully!**\n\n`;
    if (data.log && data.log.trim()) message += `**Terminal output:**\n\`\`\`\n${data.log}\n\`\`\`\n\n`;
    message += `📎 [Download ${data.filename}](${data.downloadUrl})\n\n_Import in GNS3 → File → Import portable project._`;
    return message;
  } else {
    throw new Error(data.error || 'Unknown error');
  }
}

export async function askGeminiStream(conversationHistory, imageDataList, onChunk) {
  let lastUserMessage = '';
  let previousUserMessages = [];
  for (let i = conversationHistory.length - 1; i >= 0; i--) {
    if (conversationHistory[i].role === 'user') {
      if (!lastUserMessage) lastUserMessage = conversationHistory[i].content;
      else previousUserMessages.unshift(conversationHistory[i].content);
    }
  }
  const context = previousUserMessages.slice(-2).join(' | ');
  const fullPrompt = context ? `Previous context: ${context}\n\nCurrent request: ${lastUserMessage}` : lastUserMessage;

  if (!fullPrompt || fullPrompt.trim() === '') {
    onChunk('⚠️ No prompt provided.');
    return;
  }

  const token = getAuthToken();
  if (!token) {
    onChunk('🔐 You are not logged in. Please sign in again.');
    return;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ prompt: fullPrompt }),
    });
    const data = await response.json();
    if (!response.ok) {
      onChunk(`❌ **Pipeline failed**\n\`\`\`\n${data.details || data.error || 'Unknown error'}\n\`\`\``);
      return;
    }
    if (data.success) {
      let message = `✅ **GNS3 project generated successfully!**\n\n`;
      if (data.log && data.log.trim()) message += `**Terminal output:**\n\`\`\`\n${data.log}\n\`\`\`\n\n`;
      message += `📎 [Download ${data.filename}](${data.downloadUrl})\n\n_Import in GNS3 → File → Import portable project._`;
      onChunk(message);
    } else {
      onChunk(`❌ **Error:** ${data.error || 'Unknown error'}\n\`\`\`\n${data.details || ''}\n\`\`\``);
    }
  } catch (error) {
    console.error('Generate error:', error);
    onChunk(`❌ **Network error:** ${error.message}`);
  }
}

export async function uploadProjectFile(file) {
  const token = getAuthToken();
  if (!token) throw new Error('Not authenticated');
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE_URL}/api/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Upload failed');
  }
  return response.json();
}