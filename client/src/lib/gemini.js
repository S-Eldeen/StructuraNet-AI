import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({ apiKey: import.meta.env.VITE_GEMINI_PUBLIC_KEY });

const safetySettings = [
  {
    category: "HARM_CATEGORY_HATE_SPEECH",
    threshold: "BLOCK_LOW_AND_ABOVE",
  },
];

// قائمة النماذج البديلة للنصوص (حسب الأولوية)
const TEXT_MODELS = [
  "gemini-3-flash-preview",
  "gemini-2.5-flash",
  "gemini-2.0-flash",
  "gemini-1.5-flash"
];

// قائمة النماذج البديلة للصور (توليد الصور)
const IMAGE_MODELS = [
  "gemini-3.1-flash-image-preview",
  "gemini-2.5-flash-image"
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

// دالة إعادة المحاولة مع التراجع الأسي (لنموذج محدد)
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
      console.log(`⚠️ Retrying after ${delay}ms... (attempt ${attempt + 1}/${maxRetries - 1})`);
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

// دالة مساعدة لتجربة عدة نماذج للطلبات النصية
async function tryModelsForText(promptParts, imageMode = false) {
  const models = imageMode ? IMAGE_MODELS : TEXT_MODELS;
  let lastError;
  for (const model of models) {
    try {
      console.log(`🔄 Trying model: ${model}`);
      const response = await callWithRetry(async () => {
        const result = await ai.models.generateContent({
          model: model,
          contents: promptParts,
          config: { safetySettings, systemInstruction: { parts: [{ text: systemInstruction }] } },
        });
        return result;
      });
      console.log(`✅ Success with model: ${model}`);
      return response;
    } catch (error) {
      console.warn(`❌ Model ${model} failed:`, error.message);
      lastError = error;
      if (error.message?.includes('429') || error.message?.includes('quota')) {
        console.log(`Quota exhausted for ${model}, trying next...`);
        continue;
      }
      throw error;
    }
  }
  throw lastError;
}

// إرسال طلب عادي (غير متدفق) – مع دعم تعليمات النظام وتبديل النماذج
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

  const response = await tryModelsForText(parts, imageUrls.length > 0);
  return response.text;
}

// إرسال طلب متدفق مع إعادة المحاولة وتبديل النماذج
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

  const models = imageUrls.length > 0 ? IMAGE_MODELS : TEXT_MODELS;
  let lastError;
  for (const model of models) {
    try {
      console.log(`🔄 Streaming with model: ${model}`);
      await callWithRetry(async () => {
        const stream = await ai.models.generateContentStream({
          model: model,
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
      console.log(`✅ Streaming succeeded with model: ${model}`);
      return;
    } catch (error) {
      console.warn(`❌ Streaming model ${model} failed:`, error.message);
      lastError = error;
      if (error.message?.includes('429') || error.message?.includes('quota')) {
        console.log(`Quota exhausted for ${model}, trying next...`);
        continue;
      }
      throw error;
    }
  }
  throw lastError;
}

// ✅ دالة لدعم المحادثات المتعددة (مع التاريخ) وتوليد الصور مع تبديل النماذج
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

  const models = newImages.length > 0 ? IMAGE_MODELS : TEXT_MODELS;
  let lastError;
  for (const model of models) {
    try {
      console.log(`🔄 History+Images with model: ${model}`);
      const response = await callWithRetry(async () => {
        return await ai.models.generateContent({
          model: model,
          contents: contents,
          config: {
            safetySettings,
            systemInstruction: { parts: [{ text: systemInstruction }] },
          },
        });
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

      console.log(`✅ History+Images succeeded with model: ${model}`);
      return { text: fullText, images };
    } catch (error) {
      console.warn(`❌ History+Images model ${model} failed:`, error.message);
      lastError = error;
      if (error.message?.includes('429') || error.message?.includes('quota')) {
        console.log(`Quota exhausted for ${model}, trying next...`);
        continue;
      }
      throw error;
    }
  }
  throw lastError;
}