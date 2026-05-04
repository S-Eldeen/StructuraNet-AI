import { GoogleGenAI } from "@google/genai";

const GEMINI_KEY = import.meta.env.VITE_GEMINI_PUBLIC_KEY;
const OPENROUTER_KEY = import.meta.env.VITE_OPENROUTER_KEY;

const ai = GEMINI_KEY ? new GoogleGenAI({ apiKey: GEMINI_KEY }) : null;

const GEMINI_MODEL = "gemini-2.0-flash";

// ✅ أضمن اختيار للموديلات المجانية بدل 404
const OPENROUTER_MODEL = "openrouter/free";

const OPENROUTER_TIMEOUT = 20000;

const systemInstruction = `
You are StructraNet AI, an intelligent assistant specialized in networking and network design.
Answer clearly and helpfully.
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

async function callOpenRouter(conversation, imageBase64 = []) {
  if (!OPENROUTER_KEY) {
    return "حاليًا لا يمكن إنشاء رد لأن مفتاح OpenRouter غير موجود.";
  }

  try {
    const messages = [
      {
        role: "system",
        content: systemInstruction,
      },
      ...conversation.map((m, index) => {
        const isLastMessage = index === conversation.length - 1;
        const role = m.role === "assistant" ? "assistant" : "user";

        if (role === "user" && isLastMessage && imageBase64.length > 0) {
          return {
            role,
            content: [
              {
                type: "text",
                text: m.content || "Describe this image.",
              },
              ...imageBase64.map((img) => ({
                type: "image_url",
                image_url: {
                  url: `data:image/jpeg;base64,${img}`,
                },
              })),
            ],
          };
        }

        return {
          role,
          content: m.content || "",
        };
      }),
    ];

    const res = await timeoutFetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${OPENROUTER_KEY}`,
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "StructraNet AI",
      },
      body: JSON.stringify({
        model: OPENROUTER_MODEL,
        messages,
        temperature: 0.7,
        max_tokens: 800,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      console.error("OpenRouter error:", data);

      if (res.status === 429) {
        return "الضغط عالي حاليًا على OpenRouter، حاول بعد قليل.";
      }

      return "حاليًا لا يمكن إنشاء رد من OpenRouter.";
    }

    return (
      data?.choices?.[0]?.message?.content ||
      "لم يصل رد واضح من OpenRouter، حاول مرة أخرى."
    );
  } catch (err) {
    console.error("OpenRouter fetch error:", err);

    if (err.name === "AbortError") {
      return "OpenRouter استغرق وقت طويل، حاول مرة أخرى.";
    }

    return "حدث خطأ أثناء الاتصال بـ OpenRouter.";
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

  if (imageBase64.length > 0) {
    const lastUser = [...contents].reverse().find((c) => c.role === "user");

    if (lastUser) {
      lastUser.parts.push(
        ...imageBase64.map((img) => ({
          inlineData: {
            mimeType: "image/jpeg",
            data: img,
          },
        }))
      );
    }
  }

  try {
    if (!ai) throw new Error("No Gemini key");

    const stream = await ai.models.generateContentStream({
      model: GEMINI_MODEL,
      contents,
      config: {
        systemInstruction,
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

    if (!fullText.trim()) {
      throw new Error("Empty Gemini response");
    }

    return fullText;
  } catch (error) {
    console.warn("Gemini failed → switching to OpenRouter", error);

    const fallback = await callOpenRouter(conversation, imageBase64);

    safeOnChunk(fallback);
    return fallback;
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