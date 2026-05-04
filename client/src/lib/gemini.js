import { GoogleGenAI } from "@google/genai";

const GEMINI_KEY = import.meta.env.VITE_GEMINI_PUBLIC_KEY;
const OPENROUTER_KEY = import.meta.env.VITE_OPENROUTER_KEY;

const ai = GEMINI_KEY ? new GoogleGenAI({ apiKey: GEMINI_KEY }) : null;

const GEMINI_MODEL = "gemini-2.0-flash";

// Vision model عشان يفهم الصور
const OPENROUTER_MODEL = "openrouter/free";

const systemInstruction = `
You are StructraNet AI, an intelligent assistant specialized in networking and network design.
Answer clearly and helpfully.
`;

async function callOpenRouter(conversation, imageBase64 = []) {
  if (!OPENROUTER_KEY) {
    return "حاليًا لا يمكن إنشاء رد.";
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

    const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
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
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      console.error("OpenRouter error:", data);
      return "حاليًا لا يمكن إنشاء رد.";
    }

    return data?.choices?.[0]?.message?.content || "تعذر الحصول على رد.";
  } catch (err) {
    console.error("OpenRouter fetch error:", err);
    return "حاليًا لا يمكن إنشاء رد.";
  }
}

export async function askGeminiStream(conversation, imageBase64 = [], onChunk) {
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
        onChunk(fullText);
      }
    }

    return fullText;
  } catch (error) {
    console.warn("Gemini failed → switching to OpenRouter");

    const fallback = await callOpenRouter(conversation, imageBase64);

    onChunk(fallback);
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