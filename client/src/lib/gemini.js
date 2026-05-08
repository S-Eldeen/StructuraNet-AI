import { GoogleGenAI } from "@google/genai";

const GEMINI_KEY = import.meta.env.VITE_GEMINI_PUBLIC_KEY;
const OPENROUTER_KEY = import.meta.env.VITE_OPENROUTER_KEY;

const ai = GEMINI_KEY ? new GoogleGenAI({ apiKey: GEMINI_KEY }) : null;

const GEMINI_MODEL = "gemini-2.0-flash";
const OPENROUTER_MODEL = "openrouter/free";
const OPENROUTER_TIMEOUT = 30000;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const systemInstruction = `
You are StructraNet AI.

You must behave like a Claude-style product-building assistant.

When the user asks to build an app, system, or platform:

- Show progress steps
- Use checkmarks
- Include architecture diagram
- Be practical and structured

Prefer Arabic if the user writes Arabic.
`;

const timeoutFetch = async (url, options, timeout = OPENROUTER_TIMEOUT) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
};

// ✨ دي أهم حاجة: تحويل الرد لـ streaming وهمي
const streamTextManually = async (text, onChunk, delay = 6) => {
  let current = "";

  for (let i = 0; i < text.length; i++) {
    current += text[i];

    if (i % 3 === 0 || i === text.length - 1) {
      onChunk(current);
      await sleep(delay);
    }
  }

  return text;
};

async function callOpenRouter(conversation, imageBase64 = []) {
  if (!OPENROUTER_KEY) {
    return "❌ مفيش API key لـ OpenRouter";
  }

  try {
    const messages = [
      { role: "system", content: systemInstruction },
      ...conversation.map((m) => ({
        role: m.role === "assistant" ? "assistant" : "user",
        content: m.content || "",
      })),
    ];

    const res = await timeoutFetch(
      "https://openrouter.ai/api/v1/chat/completions",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${OPENROUTER_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: OPENROUTER_MODEL,
          messages,
          temperature: 0.75,
          max_tokens: 1600,
        }),
      }
    );

    const data = await res.json();

    if (!res.ok) {
      console.error("OpenRouter error:", data);
      return "❌ OpenRouter حصل فيه مشكلة";
    }

    return data?.choices?.[0]?.message?.content || "❌ مفيش رد";
  } catch (err) {
    console.error(err);
    return "❌ Error في OpenRouter";
  }
}

export async function askGeminiStream(
  conversation,
  imageBase64 = [],
  onChunk = () => {}
) {
  const safeOnChunk = typeof onChunk === "function" ? onChunk : () => {};

  const contents = conversation.map((msg) => ({
    role: msg.role === "user" ? "user" : "model",
    parts: [{ text: msg.content || "" }],
  }));

  try {
    // ✅ Gemini streaming الحقيقي
    if (ai) {
      const stream = await ai.models.generateContentStream({
        model: GEMINI_MODEL,
        contents,
        config: {
          systemInstruction,
          temperature: 0.75,
          maxOutputTokens: 1600,
        },
      });

      let fullText = "";

      for await (const chunk of stream) {
        const text = chunk.text;

        if (text) {
          fullText += text;
          safeOnChunk(fullText);
        }
      }

      return fullText;
    }

    throw new Error("No Gemini key");
  } catch (error) {
    console.warn("Gemini failed → OpenRouter fallback");

    const fallback = await callOpenRouter(conversation, imageBase64);

    if (!fallback) {
      const msg = "❌ مفيش رد";
      safeOnChunk(msg);
      return msg;
    }

    // 🔥 هنا الحل النهائي
    return await streamTextManually(fallback, safeOnChunk);
  }
}

export async function askGemini(text, imageBase64 = []) {
  let result = "";

  await askGeminiStream(
    [{ role: "user", content: text }],
    imageBase64,
    (chunk) => {
      result = chunk;
    }
  );

  return result;
}