import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({ apiKey: import.meta.env.VITE_GEMINI_PUBLIC_KEY });

const safetySettings = [
  {
    category: "HARM_CATEGORY_HATE_SPEECH",
    threshold: "BLOCK_LOW_AND_ABOVE",
  },
];

// تحويل رابط الصورة إلى base64
async function urlToBase64(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch image: ${response.status}`);
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

// دالة إعادة المحاولة مع التراجع الأسي
async function callWithRetry(fn, maxRetries = 5, baseDelay = 1000) {
  let lastError;
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      // تحقق إذا كان الخطأ 503
      const is503 = error.message?.includes('503') ||
                    error.message?.includes('UNAVAILABLE') ||
                    error.message?.includes('overloaded');
      if (!is503 || attempt === maxRetries - 1) throw error;
      const delay = Math.min(baseDelay * Math.pow(2, attempt), 30000);
      console.log(`⚠️ إعادة المحاولة بعد ${delay}ms... (محاولة ${attempt + 1}/${maxRetries - 1})`);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  throw lastError;
}

// إرسال طلب عادي (غير متدفق)
export async function askGemini(text, imageUrls = []) {
  const parts = [];
  if (text?.trim()) parts.push({ text });

  for (const url of imageUrls) {
    const fullUrl = import.meta.env.VITE_IMAGE_KIT_ENDPOINT + url;
    const base64 = await urlToBase64(fullUrl);
    parts.push({
      inlineData: { mimeType: "image/jpeg", data: base64 },
    });
  }

  if (parts.length === 0) throw new Error("No content to send.");

  return callWithRetry(async () => {
    const response = await ai.models.generateContent({
      model: "gemini-3-flash-preview",
      contents: parts,
      config: { safetySettings },
    });
    return response.text;
  });
}

// إرسال طلب متدفق مع إعادة المحاولة
export async function askGeminiStream(text, imageUrls = [], onChunk) {
  const parts = [];
  if (text?.trim()) parts.push({ text });

  for (const url of imageUrls) {
    const fullUrl = import.meta.env.VITE_IMAGE_KIT_ENDPOINT + url;
    const base64 = await urlToBase64(fullUrl);
    parts.push({
      inlineData: { mimeType: "image/jpeg", data: base64 },
    });
  }

  if (parts.length === 0) throw new Error("No content to send.");

  // استخدام callWithRetry لتغليف عملية التيار
  await callWithRetry(async () => {
    const stream = await ai.models.generateContentStream({
      model: "gemini-3-flash-preview",
      contents: parts,
      config: { safetySettings },
    });

    let fullText = '';
    for await (const chunk of stream) {
      const chunkText = chunk.text;
      if (chunkText) {
        fullText += chunkText;
        onChunk(fullText);
      }
    }
    return fullText;
  });
}