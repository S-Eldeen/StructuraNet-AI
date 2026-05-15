import { GoogleGenAI } from "@google/genai";

const GEMINI_KEY = import.meta.env.VITE_GEMINI_PUBLIC_KEY;
const OPENROUTER_KEY = import.meta.env.VITE_OPENROUTER_KEY;

const ai = GEMINI_KEY ? new GoogleGenAI({ apiKey: GEMINI_KEY }) : null;

const GEMINI_MODEL = "gemini-2.0-flash";

const OPENROUTER_MODELS = [
  "openrouter/free",
  "mistralai/mistral-7b-instruct:free",
];

const GEMINI_TIMEOUT = 25000;
const OPENROUTER_TIMEOUT = 60000;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const systemInstruction = `
You are StructraNet AI.

You are a practical engineering and product-building assistant.

Rules:
- Answer only based on the current user request.
- Do not reuse old projects unless the user explicitly asks.
- If the user asks for networking, give networking design only.
- If the user asks for app/system design, give app/system design only.
- Prefer Arabic if the user writes Arabic.
- Be clear, practical, and structured.
- Do not ask the user to write "كمل".
`;

const timeoutPromise = (ms, message = "TIMEOUT") =>
  new Promise((_, reject) => {
    setTimeout(() => reject(new Error(message)), ms);
  });

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

const streamTextManually = async (text, onChunk, delay = 2) => {
  let current = "";

  for (let i = 0; i < text.length; i++) {
    current += text[i];

    if (i % 8 === 0 || i === text.length - 1) {
      onChunk(current);
      await sleep(delay);
    }
  }

  return text;
};

async function callGemini(conversation, onChunk) {
  if (!ai) {
    throw new Error("NO_GEMINI_KEY");
  }

  const contents = conversation.map((msg) => ({
    role: msg.role === "user" ? "user" : "model",
    parts: [{ text: msg.content || "" }],
  }));

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
      onChunk(fullText);
    }
  }

  if (!fullText.trim()) {
    throw new Error("EMPTY_GEMINI_RESPONSE");
  }

  return fullText;
}

async function callOpenRouter(conversation) {
  if (!OPENROUTER_KEY) {
    return "❌ OpenRouter key مش موجود. تأكد من VITE_OPENROUTER_KEY في client/.env";
  }

  const messages = [
    { role: "system", content: systemInstruction },
    ...conversation.map((m) => ({
      role: m.role === "assistant" ? "assistant" : "user",
      content: m.content || "",
    })),
  ];

  for (const model of OPENROUTER_MODELS) {
    try {
      console.log("Trying OpenRouter model:", model);

      const res = await timeoutFetch(
        "https://openrouter.ai/api/v1/chat/completions",
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${OPENROUTER_KEY}`,
            "Content-Type": "application/json",
            "HTTP-Referer": window.location.origin,
            "X-Title": "StructraNet AI",
          },
          body: JSON.stringify({
            model,
            messages,
            temperature: 0.65,
            max_tokens: 1600,
          }),
        },
        OPENROUTER_TIMEOUT
      );

      const data = await res.json();

      if (!res.ok) {
        console.error(`OpenRouter error with ${model}:`, data);
        continue;
      }

      const answer = data?.choices?.[0]?.message?.content;

      if (answer && answer.trim()) {
        return answer;
      }
    } catch (err) {
      console.error(`OpenRouter failed with ${model}:`, err);
      continue;
    }
  }

  return "❌ Gemini فشل، وOpenRouter فشل أيضًا. افتح Console وشوف سبب OpenRouter error.";
}

export async function askGeminiStream(
  conversation,
  imageBase64 = [],
  onChunk = () => {}
) {
  const safeOnChunk = typeof onChunk === "function" ? onChunk : () => {};

  const cleanConversation = conversation
    .filter((msg) => msg?.content)
    .slice(-4);

  try {
    return await Promise.race([
      callGemini(cleanConversation, safeOnChunk),
      timeoutPromise(GEMINI_TIMEOUT, "GEMINI_TIMEOUT"),
    ]);
  } catch (error) {
    console.warn("Gemini failed → switching to OpenRouter", error);

    const fallback = await callOpenRouter(cleanConversation);

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