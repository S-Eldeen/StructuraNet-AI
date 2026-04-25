import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({
  apiKey: import.meta.env.VITE_GEMINI_PUBLIC_KEY,
});

const safetySettings = [
  {
    category: "HARM_CATEGORY_HATE_SPEECH",
    threshold: "BLOCK_LOW_AND_ABOVE",
  },
];

const TEXT_MODELS = [
  "gemini-3-flash-preview",
  "gemini-2.5-flash",
  "gemini-2.0-flash",
];

const IMAGE_MODELS = [
  "gemini-3.1-flash-image-preview",
  "gemini-2.5-flash-image",
];

function isIdentityQuestion(prompt) {
  if (typeof prompt !== "string") return false;

  const keywords = [
    "who are you",
    "what is your name",
    "tell me about yourself",
    "who created you",
    "what are you",
    "your name",
    "introduce yourself",
    "مين أنت",
    "ما اسمك",
    "عرف نفسك",
    "من أنت",
    "قوللي عن نفسك",
  ];

  const lowerPrompt = prompt.toLowerCase().trim();
  return keywords.some((keyword) => lowerPrompt.includes(keyword));
}

async function urlToBase64(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Failed to fetch image: ${response.status}`);
  }

  const blob = await response.blob();

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function callWithRetry(fn, maxRetries = 5, baseDelay = 1000) {
  let lastError;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      const is503 =
        error.message?.includes("503") ||
        error.message?.includes("UNAVAILABLE") ||
        error.message?.includes("overloaded");

      if (!is503 || attempt === maxRetries - 1) {
        throw error;
      }

      const delay = Math.min(baseDelay * Math.pow(2, attempt), 30000);
      console.log(`⚠️ Retrying after ${delay}ms...`);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError;
}

const systemInstruction = `
You are an intelligent assistant specialized in network design; your name is StructranetAI.
If the user asks for your name, tell them that your name is StructranetAI, not Gemini.
Your mission is to assist users with questions regarding networking, network design,
design analysis, and image generation upon request.
`;

function getFriendlyErrorMessage(error) {
  const message = error?.message || "";

  if (
    message.includes("429") ||
    message.includes("quota") ||
    message.includes("RESOURCE_EXHAUSTED")
  ) {
    return "عذراً، تم استنفاد عدد الطلبات المجانية لهذا اليوم. يرجى المحاولة لاحقاً أو ترقية الحساب.";
  }

  if (
    message.includes("503") ||
    message.includes("UNAVAILABLE") ||
    message.includes("overloaded")
  ) {
    return "الخدمة مشغولة حالياً، يرجى المحاولة مرة أخرى بعد قليل.";
  }

  if (message.includes("404") || message.includes("not found")) {
    return "النموذج المطلوب غير متوفر حالياً. يرجى تحديث التطبيق أو المحاولة لاحقاً.";
  }

  if (message.includes("403") || message.includes("PERMISSION_DENIED")) {
    return "مشكلة في مفتاح API. يرجى التواصل مع الدعم الفني.";
  }

  return "حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى.";
}

async function tryModelsForText(contents, imageMode = false) {
  const models = imageMode ? IMAGE_MODELS : TEXT_MODELS;
  let lastError;

  for (const model of models) {
    try {
      console.log(`🔄 Trying model: ${model}`);

      const response = await callWithRetry(async () => {
        return await ai.models.generateContent({
          model,
          contents,
          config: {
            safetySettings,
            systemInstruction: {
              parts: [{ text: systemInstruction }],
            },
          },
        });
      });

      console.log(`✅ Success with model: ${model}`);
      return response;
    } catch (error) {
      console.warn(`❌ Model ${model} failed:`, error.message);
      lastError = error;

      if (
        error.message?.includes("429") ||
        error.message?.includes("quota") ||
        error.message?.includes("503") ||
        error.message?.includes("UNAVAILABLE") ||
        error.message?.includes("404") ||
        error.message?.includes("not found")
      ) {
        continue;
      }

      throw error;
    }
  }

  throw new Error(getFriendlyErrorMessage(lastError));
}

export async function askGemini(text, imageUrls = []) {
  if (text && isIdentityQuestion(text)) {
    return "Hello! I'm StructranetAI, an intelligent assistant specialized in network design. I can help you design networks, analyze topologies, explain protocols, and generate network diagrams.";
  }

  const parts = [];

  if (text?.trim()) {
    parts.push({ text });
  }

  for (const url of imageUrls) {
    const fullUrl = import.meta.env.VITE_IMAGE_KIT_ENDPOINT + url;
    const base64 = await urlToBase64(fullUrl);

    parts.push({
      inlineData: {
        mimeType: "image/jpeg",
        data: base64,
      },
    });
  }

  if (parts.length === 0) {
    throw new Error("No content to send.");
  }

  const response = await tryModelsForText(parts, imageUrls.length > 0);
  return response.text;
}

export async function askGeminiStream(conversation, imageUrls = [], onChunk) {
  if (typeof conversation === "string") {
    conversation = [{ role: "user", content: conversation }];
  }

  const lastUserMessage = [...conversation]
    .reverse()
    .find((msg) => msg.role === "user");

  if (lastUserMessage?.content && isIdentityQuestion(lastUserMessage.content)) {
    const identityResponse =
      "Hello! I'm StructranetAI, an intelligent assistant specialized in network design. I can help you design networks, analyze topologies, explain protocols, and generate network diagrams.";

    onChunk(identityResponse);
    return identityResponse;
  }

  const contents = [];

  for (const msg of conversation) {
    if (!msg.content) continue;

    contents.push({
      role: msg.role === "user" ? "user" : "model",
      parts: [{ text: msg.content }],
    });
  }

  if (imageUrls.length > 0) {
    const imageParts = await Promise.all(
      imageUrls.map(async (url) => {
        const fullUrl = import.meta.env.VITE_IMAGE_KIT_ENDPOINT + url;
        const base64 = await urlToBase64(fullUrl);

        return {
          inlineData: {
            mimeType: "image/jpeg",
            data: base64,
          },
        };
      })
    );

    const lastUser = [...contents]
      .reverse()
      .find((item) => item.role === "user");

    if (lastUser) {
      lastUser.parts.push(...imageParts);
    }
  }

  if (contents.length === 0) {
    throw new Error("No content to send.");
  }

  const models = imageUrls.length > 0 ? IMAGE_MODELS : TEXT_MODELS;
  let lastError;

  for (const model of models) {
    try {
      console.log(`🔄 Streaming with model: ${model}`);

      const fullText = await callWithRetry(async () => {
        const stream = await ai.models.generateContentStream({
          model,
          contents,
          config: {
            safetySettings,
            systemInstruction: {
              parts: [{ text: systemInstruction }],
            },
          },
        });

        let accumulated = "";

        for await (const chunk of stream) {
          const chunkText = chunk.text;

          if (chunkText) {
            accumulated += chunkText;
            onChunk(accumulated);
          }
        }

        return accumulated;
      });

      console.log(`✅ Streaming succeeded with model: ${model}`);
      return fullText;
    } catch (error) {
      console.warn(`❌ Streaming model ${model} failed:`, error.message);
      lastError = error;

      if (
        error.message?.includes("429") ||
        error.message?.includes("quota") ||
        error.message?.includes("503") ||
        error.message?.includes("UNAVAILABLE") ||
        error.message?.includes("404") ||
        error.message?.includes("not found")
      ) {
        continue;
      }

      throw error;
    }
  }

  throw new Error(getFriendlyErrorMessage(lastError));
}