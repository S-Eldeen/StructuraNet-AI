import { useState, forwardRef, useImperativeHandle, useRef, useEffect } from "react";
import { askGeminiStream } from "../../lib/gemini";
import "./newPrompt.css";

const NewPrompt = forwardRef(({ addMessage, setIsTyping, chatId, history = [], onRegenerate }, ref) => {
  const [text, setText]           = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [images, setImages]       = useState([]);
  const [isListening, setIsListening] = useState(false);
  const [showUploadMenu, setShowUploadMenu] = useState(false);

  const imageInputRef = useRef(null);
  const fileInputRef  = useRef(null);
  const menuRef       = useRef(null);

  /* ── Close menu on outside click ── */
  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setShowUploadMenu(false);
      }
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
          data: result.split(",")[1],
          mimeType: file.type || "image/jpeg",
          preview: result,
          fileName: file.name,
          isFile: !file.type.startsWith("image/"),
        });
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  const handleImageChange = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    const converted = await Promise.all(files.map(fileToBase64));
    setImages((prev) => [...prev, ...converted]);
    e.target.value = "";
    setShowUploadMenu(false);
  };

  const handleFileChange = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    const converted = await Promise.all(files.map(fileToBase64));
    setImages((prev) => [...prev, ...converted]);
    e.target.value = "";
    setShowUploadMenu(false);
  };

  const removeImage = (index) => setImages((prev) => prev.filter((_, i) => i !== index));

  const startListening = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("المتصفح لا يدعم التعرف على الصوت. يرجى استخدام Chrome أو Edge.");
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = "ar-EG";
    recognition.continuous = false;
    recognition.interimResults = false;
    setIsListening(true);
    recognition.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      setText((prev) => prev + (prev ? " " : "") + transcript);
      setIsListening(false);
    };
    recognition.onerror = () => { setIsListening(false); };
    recognition.onend   = () => { setIsListening(false); };
    recognition.start();
  };

  /* ── Core AI call ── */
  const runAiCall = async ({ userText, dbImages, imageBase64Only, userMessage, currentHistory }) => {
    const token = localStorage.getItem("token");
    setIsLoading(true);
    setIsTyping(true);
    const aiMessageId = Date.now() + Math.random();

    addMessage({ role: "assistant", content: "", id: aiMessageId, streaming: true, images: [] });

    try {
      let accumulatedText = "";
      const conversation = [
        ...currentHistory
          .filter((msg) => msg.content && !msg.streaming)
          .map((msg) => ({ role: msg.role === "user" ? "user" : "assistant", content: msg.content })),
        { role: "user", content: userText || "Describe this." },
      ];

      await askGeminiStream(conversation, imageBase64Only, (partialText) => {
        accumulatedText = partialText;
        addMessage({ role: "assistant", content: accumulatedText, id: aiMessageId, streaming: true, images: [] }, true);
      });

      addMessage({ role: "assistant", content: accumulatedText, id: aiMessageId, streaming: false, images: [] }, true);

      if (chatId && token) {
        await fetch(`http://localhost:3000/api/chats/${chatId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({
            messages: [userMessage, { role: "assistant", content: accumulatedText, images: [] }],
          }),
        });
      }
    } catch (error) {
      console.error("AI Error:", error);
      addMessage({ role: "assistant", content: "عذراً، حدث خطأ. حاول مرة أخرى.", id: aiMessageId, streaming: false, images: [] }, true);
    } finally {
      setIsLoading(false);
      setIsTyping(false);
    }
  };

  /* ── Expose regenerate ── */
  useImperativeHandle(ref, () => ({
    regenerate: async (lastUserMsg, currentHistory) => {
      if (isLoading) return;
      const userText = lastUserMsg.content || "";
      const dbImages = lastUserMsg.images || [];
      const imageBase64Only = dbImages.map((img) => img.data);
      await runAiCall({ userText, dbImages, imageBase64Only, userMessage: lastUserMsg, currentHistory });
    },
  }));

  /* ── Submit ── */
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isLoading) return;
    const token = localStorage.getItem("token");
    if (!token) { window.location.href = "/sign-in"; return; }
    const hasText = text.trim() !== "";
    const hasImages = images.length > 0;
    if (!hasText && !hasImages) return;

    const dbImages        = images.map((img) => ({ data: img.data, mimeType: img.mimeType }));
    const imageBase64Only = images.map((img) => img.data);
    const userMessage     = { role: "user", content: text, images: dbImages };

    addMessage(userMessage);
    const currentText = text;
    setText("");
    setImages([]);

    await runAiCall({ userText: currentText, dbImages, imageBase64Only, userMessage, currentHistory: history });
  };

  return (
    <div className="newPrompt">
      <form onSubmit={handleSubmit}>

        {/* Previews */}
        {images.length > 0 && (
          <div className="previews-row">
            {images.map((img, idx) => (
              <div key={idx} className="preview-item large">
                {img.isFile ? (
                  <div className="file-preview">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14 2 14 8 20 8"/>
                    </svg>
                    <span className="file-name">{img.fileName}</span>
                  </div>
                ) : (
                  <img src={img.preview} alt="preview" />
                )}
                <button type="button" className="remove-preview" onClick={() => removeImage(idx)}>✕</button>
              </div>
            ))}
          </div>
        )}

        <div className="input-row">

          {/* Upload button with dropdown */}
          <div className="upload-wrapper" ref={menuRef}>
            <button
              type="button"
              className="upload-btn"
              onClick={() => setShowUploadMenu((p) => !p)}
              disabled={isLoading}
              title="Attach"
            >
              <img src="/attachment.png" alt="upload" />
            </button>

            {showUploadMenu && (
              <div className="upload-menu">
                <button
                  type="button"
                  className="upload-menu-item"
                  onClick={() => imageInputRef.current?.click()}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M16 5h6"/><path d="M19 2v6"/>
                    <path d="M21 11.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7.5"/>
                    <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
                    <circle cx="9" cy="9" r="2"/>
                  </svg>
                  Add Image
                </button>

                <button
                  type="button"
                  className="upload-menu-item"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M11.35 22H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.706.706l3.588 3.588A2.4 2.4 0 0 1 20 8v5.35"/>
                    <path d="M14 2v5a1 1 0 0 0 1 1h5"/>
                    <path d="M14 19h6"/><path d="M17 16v6"/>
                  </svg>
                  Add File
                </button>
              </div>
            )}

            {/* Hidden inputs */}
            <input ref={imageInputRef} type="file" multiple accept="image/*" onChange={handleImageChange} hidden />
            <input ref={fileInputRef}  type="file" multiple accept=".pdf,.doc,.docx,.txt,.csv,.json,.xml,.zip" onChange={handleFileChange} hidden />
          </div>

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