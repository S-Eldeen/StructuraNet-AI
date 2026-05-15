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

    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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

    const isBuildRequest = (input = "") => {
      const lower = input.toLowerCase();

      return (
        lower.includes("build") ||
        lower.includes("create") ||
        lower.includes("make") ||
        lower.includes("develop") ||
        lower.includes("app") ||
        lower.includes("application") ||
        lower.includes("system") ||
        lower.includes("dashboard") ||
        lower.includes("platform") ||
        lower.includes("website") ||
        lower.includes("tool") ||
        lower.includes("ai") ||
        lower.includes("frontend") ||
        lower.includes("backend") ||
        lower.includes("ui") ||
        lower.includes("ux") ||
        lower.includes("diagram") ||
        lower.includes("architecture") ||
        lower.includes("code") ||
        lower.includes("api") ||
        lower.includes("database") ||
        lower.includes("network") ||
        lower.includes("networking") ||
        lower.includes("router") ||
        lower.includes("switch") ||
        lower.includes("topology") ||
        lower.includes("branch") ||
        lower.includes("company") ||
        input.includes("تطبيق") ||
        input.includes("نظام") ||
        input.includes("موقع") ||
        input.includes("منصة") ||
        input.includes("أداة") ||
        input.includes("اداة") ||
        input.includes("ذكاء") ||
        input.includes("واجهة") ||
        input.includes("فرونت") ||
        input.includes("باك") ||
        input.includes("ديزاين") ||
        input.includes("تصميم") ||
        input.includes("اعمل") ||
        input.includes("أعمل") ||
        input.includes("ابني") ||
        input.includes("أنشئ") ||
        input.includes("انشئ") ||
        input.includes("ارسم") ||
        input.includes("داياجرام") ||
        input.includes("مخطط") ||
        input.includes("كود") ||
        input.includes("أكواد") ||
        input.includes("اكواد") ||
        input.includes("قاعدة بيانات") ||
        input.includes("شبكة") ||
        input.includes("سويتش") ||
        input.includes("راوتر") ||
        input.includes("شركة") ||
        input.includes("فرع")
      );
    };

    const typeStage = async (aiMessageId, currentText, stageTitle, stageBody) => {
      let localText = `${currentText}\n\n## ${stageTitle}...\n`;

      addMessage(
        {
          role: "assistant",
          content: localText,
          id: aiMessageId,
          streaming: true,
          images: [],
        },
        true
      );

      await sleep(300);

      let typed = "";

      for (let i = 0; i < stageBody.length; i++) {
        typed += stageBody[i];

        if (i % 5 === 0 || i === stageBody.length - 1) {
          addMessage(
            {
              role: "assistant",
              content: localText + typed,
              id: aiMessageId,
              streaming: true,
              images: [],
            },
            true
          );

          await sleep(5);
        }
      }

      localText = `${currentText}\n\n## ${stageTitle} ✔\n${stageBody}`;

      addMessage(
        {
          role: "assistant",
          content: localText,
          id: aiMessageId,
          streaming: true,
          images: [],
        },
        true
      );

      await sleep(350);
      return localText;
    };

    const buildPrompt = (userText) => {
      return `
You are StructuraNet AI.

The user request is:
${userText}

Important rules:
- Do NOT reuse any previous project idea unless the user explicitly asks for it.
- Answer only based on the current user request.
- If the user asks for a network design, produce a complete networking design, not a software app.
- Prefer Arabic explanation if the user writes Arabic.
- Include diagrams using diagram code blocks when useful.
- Include device counts, ports, topology, IP plan, VLANs, security, and file naming when relevant.
`;
    };

    const withTimeout = (promise, ms = 120000) => {
      let timeoutId;

      const timeoutPromise = new Promise((_, reject) => {
        timeoutId = setTimeout(() => {
          reject(new Error("AI_TIMEOUT"));
        }, ms);
      });

      return Promise.race([promise, timeoutPromise]).finally(() => {
        clearTimeout(timeoutId);
      });
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
        content: "",
        id: aiMessageId,
        streaming: true,
        images: [],
      });

      try {
        let finalText = "";

        // مهم: بنبعت آخر 6 رسائل فقط من نفس الشات، عشان ما يخلطش مشاريع قديمة
        const baseHistory = [
          ...currentHistory
            .filter((msg) => msg.content && !msg.streaming)
            .slice(-6)
            .map((msg) => ({
              role: msg.role === "user" ? "user" : "assistant",
              content: msg.content,
            })),
        ];

        await withTimeout(
          askGeminiStream(
            [
              ...baseHistory,
              {
                role: "user",
                content: buildPrompt(userText || "Describe this."),
              },
            ],
            imageBase64Only,
            (partialText) => {
              finalText = partialText || "";

              addMessage(
                {
                  role: "assistant",
                  content: finalText,
                  id: aiMessageId,
                  streaming: true,
                  images: [],
                },
                true
              );
            }
          ),
          120000
        );

        const displayedText = finalText || "لم يصل رد واضح، حاول مرة أخرى.";

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
            content:
              "❌ حصل خطأ، لكن الرد السابق لن يتم مسحه. جرّب مرة تانية أو راجع مفتاح Gemini/OpenRouter.",
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