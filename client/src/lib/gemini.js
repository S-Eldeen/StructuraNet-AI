import { GoogleGenAI } from "@google/genai";

const apiKey = import.meta.env.VITE_GEMINI_PUBLIC_KEY;

console.log("Gemini key start:", apiKey?.slice(0, 12));

const ai = new GoogleGenAI({
  apiKey,
});

const safetySettings = [
  {
    category: "HARM_CATEGORY_HATE_SPEECH",
    threshold: "BLOCK_LOW_AND_ABOVE",
  },
];

const MODELS = [
  "gemini-1.5-flash",
  "gemini-2.0-flash",
];

const systemInstruction = `
You are StructranetAI, an intelligent assistant specialized in networking and network design.
`;

function getFriendlyError(error) {
  const msg = error?.message || "";

  if (msg.includes("API key expired") || msg.includes("API_KEY_INVALID")) {
    return "مفتاح Gemini غير صالح أو منتهي. تأكد إنك حطيت المفتاح الجديد في client/.env ثم أعد تشغيل npm run dev.";
  }

  if (msg.includes("429") || msg.includes("quota")) {
    return "تم استهلاك الحد المجاني. حاول لاحقاً أو استخدم API key جديد.";
  }

  if (msg.includes("503") || msg.includes("UNAVAILABLE")) {
    return "السيرفر مشغول حالياً، حاول تاني.";
  }

  return "حصل خطأ، حاول مرة تانية.";
}

export async function askGeminiStream(conversation, imageBase64 = [], onChunk) {
  if (!apiKey) {
    throw new Error("Missing VITE_GEMINI_PUBLIC_KEY in client/.env");
  }

  const contents = [];

  for (const msg of conversation) {
    contents.push({
      role: msg.role === "user" ? "user" : "model",
      parts: [{ text: msg.content || "" }],
    });
  }

  if (imageBase64.length > 0) {
    const imageParts = imageBase64.map((img) => ({
      inlineData: {
        mimeType: "image/jpeg",
        data: img,
      },
    }));

    const lastUser = [...contents].reverse().find((c) => c.role === "user");

    if (lastUser) {
      lastUser.parts.push(...imageParts);
    }
  }

  let lastError;

  for (const model of MODELS) {
    try {
      console.log("Trying Gemini model:", model);

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

      let fullText = "";

      for await (const chunk of stream) {
        const text = chunk.text;
        if (text) {
          fullText += text;
          onChunk(fullText);
        }
      }

      console.log("Gemini success:", model);
      return fullText;
    } catch (err) {
      console.warn("Gemini failed:", model, err.message);
      lastError = err;
    }
  }

  throw new Error(getFriendlyError(lastError));
}

export async function askGemini(text, imageBase64 = []) {
  let finalText = "";

  await askGeminiStream(
    [{ role: "user", content: text }],
    imageBase64,
    (chunk) => {
      finalText = chunk;
    }
  );

  return finalText;
}