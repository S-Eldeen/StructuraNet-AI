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

// تعليمات النظام – يقدم نفسه باسم StructranetAI
const systemInstruction = `You are an intelligent assistant specialized in network design; your name is StructranetAI.
 If the user asks for your name, tell them that your name is StructranetAI (not Gemini). 
Your mission is to assist users with their questions regarding networking, network design,
 design analysis, and image generation upon request. If the user requests an image 
(e.g., 'draw a network' or 'generate a network image'), use the appropriate model to generate it.`;

// إرسال طلب عادي (غير متدفق) – مع دعم تعليمات النظام
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
      model: "gemini-3-flash-preview", // يمكن تغييره إلى gemini-3.1-flash-image-preview إذا أردت توليد صور
      contents: parts,
      config: { safetySettings, systemInstruction: { parts: [{ text: systemInstruction }] } },
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

  await callWithRetry(async () => {
    const stream = await ai.models.generateContentStream({
      model: "gemini-3-flash-preview",
      contents: parts,
      config: { safetySettings, systemInstruction: { parts: [{ text: systemInstruction }] } },
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

// ✅ دالة جديدة لدعم المحادثات المتعددة (مع التاريخ) وتوليد الصور
export async function askGeminiWithHistory(messages, newMessageText, newImages = []) {
  const imageParts = await Promise.all(
    newImages.map(async (url) => {
      const fullUrl = import.meta.env.VITE_IMAGE_KIT_ENDPOINT + url;
      const base64 = await urlToBase64(fullUrl);
      return {
        inlineData: { mimeType: "image/jpeg", data: base64 },
      };
    })
  );

  const contents = [];

  for (const msg of messages) {
    const parts = [];
    if (msg.content) parts.push({ text: msg.content });
    contents.push({
      role: msg.role === 'user' ? 'user' : 'model',
      parts,
    });
  }

  const newParts = [];
  if (newMessageText) newParts.push({ text: newMessageText });
  newParts.push(...imageParts);
  contents.push({ role: 'user', parts: newParts });

  return callWithRetry(async () => {
    const response = await ai.models.generateContent({
      model: "gemini-3.1-flash-image-preview", // نموذج يدعم توليد الصور
      contents: contents,
      config: {
        safetySettings,
        systemInstruction: { parts: [{ text: systemInstruction }] },
      },
    });

    let fullText = '';
    const images = [];

    if (response.candidates && response.candidates[0] && response.candidates[0].content) {
      for (const part of response.candidates[0].content.parts) {
        if (part.text) {
          fullText += part.text;
        } else if (part.inlineData) {
          const mimeType = part.inlineData.mimeType || 'image/png';
          const data = part.inlineData.data;
          const dataUrl = `data:${mimeType};base64,${data}`;
          images.push(dataUrl);
        }
      }
    }

    return { text: fullText, images };
  });
}