import { useState, forwardRef, useImperativeHandle } from "react";
import { askGeminiStream } from "../../lib/gemini";
import "./newPrompt.css";

const NewPrompt = forwardRef(({ addMessage, setIsTyping, chatId, history = [], onRegenerate }, ref) => {
  const [text, setText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [images, setImages] = useState([]);
  const [isListening, setIsListening] = useState(false);

  const fileToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result;
        resolve({
          data: result.split(",")[1],
          mimeType: file.type || "image/jpeg",
          preview: result,
        });
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  const handleFileChange = async (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    const convertedImages = await Promise.all(files.map(fileToBase64));
    setImages((prev) => [...prev, ...convertedImages]);
    e.target.value = "";
  };

  const removeImage = (index) => {
    setImages((prev) => prev.filter((_, i) => i !== index));
  };

  const startListening = () => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert("المتصفح لا يدعم التعرف على الصوت. يرجى استخدام Chrome أو Edge.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "ar-EG";
    recognition.continuous = false;
    recognition.interimResults = false;

    setIsListening(true);

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setText((prev) => prev + (prev ? " " : "") + transcript);
      setIsListening(false);
    };

    recognition.onerror = () => {
      setIsListening(false);
      alert("حدث خطأ أثناء التعرف على الصوت. حاول مرة أخرى.");
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.start();
  };

  // ── Core AI call (reused by submit + regenerate) ──────────────────────────
  const runAiCall = async ({ userText, userImages, dbImages, imageBase64Only, userMessage, currentHistory }) => {
    const token = localStorage.getItem("token");

    setIsLoading(true);
    setIsTyping(true);

    const aiMessageId = Date.now() + Math.random();

    addMessage({
      role: "assistant",
      content: "",
      id: aiMessageId,
      streaming: true,
      images: [],
    });

    try {
      let accumulatedText = "";

      const conversation = [
        ...currentHistory
          .filter((msg) => msg.content && !msg.streaming)
          .map((msg) => ({
            role: msg.role === "user" ? "user" : "assistant",
            content: msg.content,
          })),
        {
          role: "user",
          content: userText || "Describe this image.",
        },
      ];

      await askGeminiStream(conversation, imageBase64Only, (partialText) => {
        accumulatedText = partialText;
        addMessage(
          {
            role: "assistant",
            content: accumulatedText,
            id: aiMessageId,
            streaming: true,
            images: [],
          },
          true
        );
      });

      const assistantMessage = {
        role: "assistant",
        content: accumulatedText,
        id: aiMessageId,
        streaming: false,
        images: [],
      };

      addMessage(assistantMessage, true);

      if (chatId && token) {
        await fetch(`http://localhost:3000/api/chats/${chatId}/messages`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            messages: [
              userMessage,
              { role: "assistant", content: accumulatedText, images: [] },
            ],
          }),
        });
      }
    } catch (error) {
      console.error("AI Error:", error);
      addMessage(
        {
          role: "assistant",
          content: "عذراً، حدث خطأ. حاول مرة أخرى.",
          id: aiMessageId,
          streaming: false,
          images: [],
        },
        true
      );
    } finally {
      setIsLoading(false);
      setIsTyping(false);
    }
  };

  // ── Expose regenerate to parent via ref ───────────────────────────────────
  useImperativeHandle(ref, () => ({
    regenerate: async (lastUserMsg, currentHistory) => {
      if (isLoading) return;

      const userText = lastUserMsg.content || "";
      const dbImages = lastUserMsg.images || [];
      const imageBase64Only = dbImages.map((img) => img.data);

      await runAiCall({
        userText,
        userImages: [],
        dbImages,
        imageBase64Only,
        userMessage: lastUserMsg,
        currentHistory,
      });
    },
  }));

  // ── Normal submit ─────────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isLoading) return;

    const token = localStorage.getItem("token");
    if (!token) { window.location.href = "/sign-in"; return; }

    const hasText = text.trim() !== "";
    const hasImages = images.length > 0;
    if (!hasText && !hasImages) return;

    const dbImages = images.map((img) => ({ data: img.data, mimeType: img.mimeType }));
    const imageBase64Only = images.map((img) => img.data);

    const userMessage = { role: "user", content: text, images: dbImages };

    addMessage(userMessage);

    const currentText = text;
    setText("");
    setImages([]);

    await runAiCall({
      userText: currentText,
      userImages: images,
      dbImages,
      imageBase64Only,
      userMessage,
      currentHistory: history,
    });
  };

  return (
    <div className="newPrompt">
      <form onSubmit={handleSubmit}>
        {images.length > 0 && (
          <div className="previews-row">
            {images.map((img, idx) => (
              <div key={idx} className="preview-item large">
                <img src={img.preview} alt="preview" />
                <button
                  type="button"
                  className="remove-preview"
                  onClick={() => removeImage(idx)}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="input-row">
          <label className="upload-btn">
            <img src="/attachment.png" alt="upload" />
            <input
              type="file"
              multiple
              accept="image/*"
              onChange={handleFileChange}
              hidden
            />
          </label>

          <input
            type="text"
            className="text-input"
            placeholder={isLoading ? "Thinking..." : "Ask Structranet AI"}
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={isLoading}
          />

          <button
            type="button"
            className={`mic-btn ${isListening ? "listening" : ""}`}
            onClick={startListening}
            disabled={isLoading}
            title="إدخال صوتي"
          >
            <img src="/microphone.png" alt="mic" className="mic-icon" />
          </button>

          <button
            type="button"
            className="reload-ai-btn"
            onClick={() => onRegenerate?.()}
            disabled={isLoading || history.length === 0}
            title="إعادة توليد آخر رد"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width="20" height="20">
              <polyline points="1 4 1 10 7 10" />
              <path d="M3.51 15a9 9 0 1 0 .49-4.95" />
            </svg>
          </button>

          <button
            type="submit"
            className="send-btn"
            disabled={isLoading || (!text.trim() && images.length === 0)}
          >
            <img src="/arrow.png" alt="send" />
          </button>
        </div>
      </form>
    </div>
  );
});

NewPrompt.displayName = "NewPrompt";

export default NewPrompt;
