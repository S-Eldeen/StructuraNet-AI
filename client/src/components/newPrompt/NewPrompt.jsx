import { useState, forwardRef, useImperativeHandle, useRef, useEffect } from "react";
import { askGeminiStream } from "../../lib/gemini";
import "./newPrompt.css";

const NewPrompt = forwardRef(
  ({ addMessage, setIsTyping, chatId, history = [], onRegenerate }, ref) => {
    const [text, setText] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [images, setImages] = useState([]);
    const [isListening, setIsListening] = useState(false);
    const [showUploadMenu, setShowUploadMenu] = useState(false);

    const imageInputRef = useRef(null);
    const fileInputRef = useRef(null);
    const menuRef = useRef(null);

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

    const removeImage = (index) =>
      setImages((prev) => prev.filter((_, i) => i !== index));

    const startListening = () => {
      const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;

      if (!SpeechRecognition) {
        alert("المتصفح لا يدعم التعرف على الصوت.");
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

      recognition.onerror = () => setIsListening(false);
      recognition.onend = () => setIsListening(false);

      recognition.start();
    };

    const needsStepByStep = (input = "") => {
      const lower = input.toLowerCase();

      return (
        lower.includes("steps") ||
        lower.includes("step by step") ||
        lower.includes("roadmap") ||
        lower.includes("plan") ||
        lower.includes("how to") ||
        lower.includes("explain") ||
        input.includes("خطوات") ||
        input.includes("خطة") ||
        input.includes("اشرح") ||
        input.includes("ازاي") ||
        input.includes("إزاي") ||
        input.includes("كيف")
      );
    };

    const buildPrompt = (userText) => {
      if (needsStepByStep(userText)) {
        return `
${userText}

Instructions:
- Start with: "Let me guide you step by step"
- Explain in clear numbered steps.
- Keep the answer organized and practical.
- At the end write: "Done ✅ — you can ask me anything else."
- In the next user message, continue normally and do not wait for confirmation unless the user asks.
`;
      }

      return `
${userText}

Instructions:
- Answer normally and directly.
- Do not force a step-by-step format unless it is useful.
- Do not say that the previous task is finished again.
`;
    };

    const typeWriter = async (finalText, aiMessageId) => {
      let index = 0;
      let displayedText = "";

      await new Promise((resolve) => {
        const interval = setInterval(() => {
          if (index >= finalText.length) {
            clearInterval(interval);
            resolve();
            return;
          }

          displayedText += finalText[index];
          index++;

          addMessage(
            {
              role: "assistant",
              content: displayedText,
              id: aiMessageId,
              streaming: true,
              images: [],
            },
            true
          );
        }, 12);
      });

      return displayedText;
    };

    const runAiCall = async ({
      userText,
      dbImages,
      imageBase64Only,
      userMessage,
      currentHistory,
    }) => {
      const token = localStorage.getItem("token");

      setIsLoading(true);
      setIsTyping(true);

      const aiMessageId = Date.now() + Math.random();

      addMessage({
        role: "assistant",
        content: "🤖 I am thinking...",
        id: aiMessageId,
        streaming: true,
        images: [],
      });

      try {
        let finalText = "";

        const conversation = [
          ...currentHistory
            .filter((msg) => msg.content && !msg.streaming)
            .map((msg) => ({
              role: msg.role === "user" ? "user" : "assistant",
              content: msg.content,
            })),
          {
            role: "user",
            content: buildPrompt(userText || "Describe this."),
          },
        ];

        await askGeminiStream(conversation, imageBase64Only, (partialText) => {
          finalText = partialText;
        });

        if (!finalText.trim()) {
          finalText = "لم يصل رد واضح، حاول مرة أخرى.";
        }

        let displayedText = await typeWriter(finalText, aiMessageId);

        if (needsStepByStep(userText) && !displayedText.includes("Done")) {
          displayedText += "\n\nDone ✅ — you can ask me anything else.";
        }

        addMessage(
          {
            role: "assistant",
            content: displayedText,
            id: aiMessageId,
            streaming: false,
            images: [],
          },
          true
        );

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
                { role: "assistant", content: displayedText, images: [] },
              ],
            }),
          });
        }
      } catch (error) {
        console.error("AI Error:", error);

        addMessage(
          {
            role: "assistant",
            content: "❌ حصل خطأ، حاول تاني.",
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

    useImperativeHandle(ref, () => ({
      regenerate: async (lastUserMsg, currentHistory) => {
        if (isLoading) return;

        await runAiCall({
          userText: lastUserMsg.content || "",
          dbImages: lastUserMsg.images || [],
          imageBase64Only: lastUserMsg.images?.map((i) => i.data) || [],
          userMessage: lastUserMsg,
          currentHistory,
        });
      },
    }));

    const handleSubmit = async (e) => {
      e.preventDefault();
      if (isLoading) return;

      const token = localStorage.getItem("token");
      if (!token) {
        window.location.href = "/sign-in";
        return;
      }

      if (!text.trim() && images.length === 0) return;

      const dbImages = images.map((img) => ({
        data: img.data,
        mimeType: img.mimeType,
      }));

      const userMessage = {
        role: "user",
        content: text,
        images: dbImages,
      };

      addMessage(userMessage);

      const currentText = text;
      setText("");
      setImages([]);

      await runAiCall({
        userText: currentText,
        dbImages,
        imageBase64Only: images.map((i) => i.data),
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
                  {img.isFile ? (
                    <div className="file-preview">
                      <span className="file-name">{img.fileName}</span>
                    </div>
                  ) : (
                    <img src={img.preview} alt="preview" />
                  )}

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
                    Add Image
                  </button>

                  <button
                    type="button"
                    className="upload-menu-item"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    Add File
                  </button>
                </div>
              )}

              <input
                ref={imageInputRef}
                type="file"
                multiple
                accept="image/*"
                onChange={handleImageChange}
                hidden
              />

              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.doc,.docx,.txt,.csv,.json,.xml,.zip"
                onChange={handleFileChange}
                hidden
              />
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
  }
);

NewPrompt.displayName = "NewPrompt";
export default NewPrompt;