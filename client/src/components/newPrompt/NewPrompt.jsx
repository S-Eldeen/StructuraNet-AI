import { useState, forwardRef, useImperativeHandle, useRef, useEffect } from "react";
import { askGeminiStream } from "../../lib/gemini";
import { API_BASE_URL } from "../../config";
import "./newPrompt.css";

const NewPrompt = forwardRef(
  ({ addMessage, setIsTyping, chatId, history = [], onRegenerate }, ref) => {
    const [text,           setText]           = useState("");
    const [isLoading,      setIsLoading]      = useState(false);
    const [images,         setImages]         = useState([]);
    const [isListening,    setIsListening]    = useState(false);
    const [showUploadMenu, setShowUploadMenu] = useState(false);

    const imageInputRef = useRef(null);
    const fileInputRef  = useRef(null);
    const menuRef       = useRef(null);

    // Close upload menu on outside click
    useEffect(() => {
      const handler = (e) => {
        if (menuRef.current && !menuRef.current.contains(e.target))
          setShowUploadMenu(false);
      };
      document.addEventListener("mousedown", handler);
      return () => document.removeEventListener("mousedown", handler);
    }, []);

    const fileToBase64 = (file) =>
      new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const result = reader.result;
          resolve({
            data:     result.split(",")[1],
            mimeType: file.type || "image/jpeg",
            preview:  result,
            fileName: file.name,
            isFile:   !file.type.startsWith("image/"),
          });
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });

    const handleImageChange = async (e) => {
      const files = Array.from(e.target.files || []);
      if (!files.length) return;
      const converted = await Promise.all(files.map(fileToBase64));
      setImages(prev => [...prev, ...converted]);
      e.target.value = "";
      setShowUploadMenu(false);
    };

    const handleFileChange = async (e) => {
      const files = Array.from(e.target.files || []);
      if (!files.length) return;
      const converted = await Promise.all(files.map(fileToBase64));
      setImages(prev => [...prev, ...converted]);
      e.target.value = "";
      setShowUploadMenu(false);
    };

    const removeImage = (i) => setImages(prev => prev.filter((_, idx) => idx !== i));

    const startListening = () => {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { alert("المتصفح لا يدعم التعرف على الصوت."); return; }
      const rec = new SR();
      rec.lang = "ar-EG";
      rec.continuous = false;
      rec.interimResults = false;
      setIsListening(true);
      rec.onresult = (e) => {
        setText(prev => prev + (prev ? " " : "") + e.results[0][0].transcript);
        setIsListening(false);
      };
      rec.onerror = () => setIsListening(false);
      rec.onend   = () => setIsListening(false);
      rec.start();
    };

    // ── Core AI call ──────────────────────────────────────────────────────────
    const runAiCall = async ({ userText, imageBase64Only, userMessage, currentHistory }) => {
      setIsLoading(true);
      setIsTyping(true);

      const aiId = Date.now() + Math.random();

      // Show empty thinking bubble immediately
      addMessage({ role: "assistant", content: "", id: aiId, streaming: true, images: [] });

      try {
        let finalText = "";

        // FIX: build a clean conversation history for context (last 6 turns)
        // gemini.js will extract the last user message and use the rest as context
        // No more double-wrapping with buildPrompt + "Previous context:" prefix
        const conversation = [
          ...currentHistory
            .filter(m => m.content && !m.streaming)
            .slice(-6)
            .map(m => ({ role: m.role === "user" ? "user" : "assistant", content: m.content })),
          { role: "user", content: userText || "" },
        ];

        // 20-minute timeout (pipeline can take up to 15 min on complex designs)
        const controller = new AbortController();
        const timeoutId  = setTimeout(() => controller.abort(), 20 * 60 * 1000);

        try {
          await askGeminiStream(
            conversation,
            imageBase64Only,
            (partial) => {
              finalText = partial || "";
              addMessage({ role: "assistant", content: finalText, id: aiId, streaming: true, images: [] }, true);
            }
          );
        } finally {
          clearTimeout(timeoutId);
        }

        addMessage(
          { role: "assistant", content: finalText || "لم يصل رد واضح، حاول مرة أخرى.", id: aiId, streaming: false, images: [] },
          true
        );

        // Save user message + AI reply to DB (only if we got a real reply)
        const token = localStorage.getItem("token");
        if (chatId && token && finalText) {
          await fetch(`${API_BASE_URL}/api/chats/${chatId}/messages`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
            body: JSON.stringify({
              messages: [
                userMessage,
                { role: "assistant", content: finalText, images: [] },
              ],
            }),
          }).catch(err => console.warn("Save messages error:", err.message));
        }
      } catch (err) {
        console.error("AI Error:", err);
        const errMsg = err.name === "AbortError"
          ? "⏱️ انتهت مهلة الانتظار (20 دقيقة). جرّب طلبًا أبسط."
          : "❌ حصل خطأ في الاتصال بالـ AI. جرّب مرة تانية.";
        addMessage({ role: "assistant", content: errMsg, id: aiId, streaming: false, images: [] }, true);
      } finally {
        setIsLoading(false);
        setIsTyping(false);
      }
    };

    // Expose regenerate to parent (ChatPage)
    useImperativeHandle(ref, () => ({
      regenerate: async (lastUserMsg, currentHistory) => {
        if (isLoading) return;
        await runAiCall({
          userText:       lastUserMsg.content || "",
          imageBase64Only: lastUserMsg.images?.map(i => i.data) || [],
          userMessage:    lastUserMsg,
          currentHistory,
        });
      },
    }));

    const handleSubmit = async (e) => {
      e.preventDefault();
      if (isLoading) return;

      const token = localStorage.getItem("token");
      if (!token) { window.location.href = "/sign-in"; return; }
      if (!text.trim() && images.length === 0) return;

      const dbImages    = images.map(img => ({ data: img.data, mimeType: img.mimeType }));
      const userMessage = { role: "user", content: text, images: dbImages };

      addMessage(userMessage);
      const currentText = text;
      setText("");
      setImages([]);

      await runAiCall({
        userText:       currentText,
        imageBase64Only: images.map(i => i.data),
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
                  {img.isFile
                    ? <div className="file-preview"><span className="file-name">{img.fileName}</span></div>
                    : <img src={img.preview} alt="preview" />
                  }
                  <button type="button" className="remove-preview" onClick={() => removeImage(idx)}>✕</button>
                </div>
              ))}
            </div>
          )}

          <div className="input-row">
            {/* Attach menu */}
            <div className="upload-wrapper" ref={menuRef}>
              <button
                type="button" className="upload-btn"
                onClick={() => setShowUploadMenu(p => !p)}
                disabled={isLoading} title="Attach"
              >
                <img src="/attachment.png" alt="upload" />
              </button>
              {showUploadMenu && (
                <div className="upload-menu">
                  <button type="button" className="upload-menu-item" onClick={() => imageInputRef.current?.click()}>Add Image</button>
                  <button type="button" className="upload-menu-item" onClick={() => fileInputRef.current?.click()}>Add File</button>
                </div>
              )}
              <input ref={imageInputRef} type="file" multiple accept="image/*" onChange={handleImageChange} hidden />
              <input ref={fileInputRef}  type="file" multiple accept=".pdf,.doc,.docx,.txt,.csv,.json,.xml,.zip" onChange={handleFileChange} hidden />
            </div>

            {/* Text input */}
            <input
              type="text" className="text-input"
              placeholder={isLoading ? "Thinking..." : "Ask Structranet AI"}
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={isLoading}
            />

            {/* Mic */}
            <button
              type="button"
              className={`mic-btn ${isListening ? "listening" : ""}`}
              onClick={startListening} disabled={isLoading} title="إدخال صوتي"
            >
              <img src="/microphone.png" alt="mic" className="mic-icon" />
            </button>

            {/* Send */}
            <button
              type="submit" className="send-btn"
              disabled={isLoading || (!text.trim() && images.length === 0)}
            >
              <img src="/arrow.png" alt="send" />
            </button>
          </div>
        </form>
      </div>
    );
  }
);

NewPrompt.displayName = "NewPrompt";
export default NewPrompt;
