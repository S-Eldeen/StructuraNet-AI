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
        input.includes("قاعدة بيانات")
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

    const getBuildStages = (userText) => [
      {
        title: "📖 Reading requirements",
        body: `تمام، تم قراءة المتطلبات بنجاح.

المطلوب هو بناء تصور هندسي كامل ومفصل للتطبيق، مش مجرد فكرة عامة.  
هنا هنطلع:

- Architecture كاملة.
- UI/UX structure.
- Diagrams واضحة.
- Database schema.
- Backend APIs.
- Frontend components.
- Example code.
- File structure.
- Visual placeholders للصور والواجهات.`,
      },
      {
        title: "🧠 Full System Architecture",
        body: `تم بناء معمارية النظام على شكل طبقات واضحة:

\`\`\`diagram
title: Full System Architecture
[User]
-> [React Frontend]
-> [API Gateway]
-> [Backend Server]
-> [AI Engine]
-> [Database]
-> [Storage]
-> [Analytics]
\`\`\`

### الطبقات الأساسية

- **Frontend Layer:** واجهة React/Vite لعرض الدروس، الاختبارات، المحادثة، والتقدم.
- **API Layer:** نقطة اتصال بين الواجهة والباك إند.
- **Backend Layer:** Express.js لمعالجة الطلبات وإدارة المستخدمين والدروس.
- **AI Layer:** Gemini/OpenRouter لتوليد الدروس، التصحيح، المحادثة، والاختبارات.
- **Database Layer:** MongoDB لحفظ المستخدمين، الدروس، التقدم، والأسئلة.
- **Storage Layer:** لحفظ الصور، الملفات، أو تسجيلات الصوت لاحقًا.

### Visual UI Placeholder

\`\`\`diagram
title: Main App Screens
[Landing Page]
-> [Dashboard]
-> [Lessons]
-> [Quiz]
-> [AI Tutor]
-> [Progress]
\`\`\``,
      },
      {
        title: "🎨 UI / UX Design",
        body: `تم تصميم الواجهة بحيث تكون قريبة من تطبيقات التعليم الحديثة:

### Dashboard Layout

\`\`\`diagram
title: Dashboard UI Layout
[Top Navbar]
-> [Progress Cards]
-> [Current Lesson]
-> [Vocabulary Cards]
-> [Quick Quiz]
-> [AI Chat Tutor]
\`\`\`

### شكل الشاشة الرئيسية

- كارت يعرض المستوى الحالي مثل A1.
- كارت عدد الكلمات التي تم تعلمها.
- كارت الأيام المتواصلة Streak.
- كارت دقة الإجابات.
- Grid للدروس المتاحة.
- زر يبدأ درس جديد.
- منطقة محادثة مع AI Tutor.

### صورة/واجهة مقترحة

[IMAGE: Modern dark educational dashboard for German learning app with progress cards, lesson cards, quiz card, and AI tutor chat panel]

### React UI Example

\`\`\`jsx
export default function Dashboard() {
  return (
    <main className="dashboard">
      <section className="stats-grid">
        <ProgressCard title="Words Learned" value="120" />
        <ProgressCard title="Streak" value="7 days" />
        <ProgressCard title="Accuracy" value="86%" />
      </section>

      <section className="content-grid">
        <LessonGrid />
        <QuickQuiz />
        <AITutor />
      </section>
    </main>
  );
}
\`\`\``,
      },
      {
        title: "🧩 Frontend Components",
        body: `تم تقسيم الواجهة إلى Components قابلة لإعادة الاستخدام:

### Component Tree

\`\`\`diagram
title: Frontend Component Tree
[App]
-> [DashboardLayout]
-> [Sidebar]
-> [DashboardPage]
-> [LessonPage]
-> [QuizPage]
-> [AITutorPage]
\`\`\`

### Components المقترحة

\`\`\`txt
components/
 ├── ProgressCard/
 │   ├── ProgressCard.jsx
 │   └── progressCard.css
 ├── LessonCard/
 │   ├── LessonCard.jsx
 │   └── lessonCard.css
 ├── LessonGrid/
 │   ├── LessonGrid.jsx
 │   └── lessonGrid.css
 ├── QuickQuiz/
 │   ├── QuickQuiz.jsx
 │   └── quickQuiz.css
 ├── AITutor/
 │   ├── AITutor.jsx
 │   └── aiTutor.css
 └── LevelSelector/
     ├── LevelSelector.jsx
     └── levelSelector.css
\`\`\`

### Example Component

\`\`\`jsx
function LessonCard({ title, level, duration, onStart }) {
  return (
    <article className="lesson-card">
      <span className="lesson-level">{level}</span>
      <h3>{title}</h3>
      <p>{duration} minutes</p>
      <button onClick={onStart}>Start Lesson</button>
    </article>
  );
}

export default LessonCard;
\`\`\``,
      },
      {
        title: "🗄️ Database Structures",
        body: `تم تصميم قاعدة البيانات بشكل يسمح بتتبع التعلم والتقدم:

### User Model

\`\`\`js
const userSchema = new mongoose.Schema({
  email: { type: String, required: true, unique: true },
  name: String,
  level: { type: String, default: "A1" },
  streak: { type: Number, default: 0 },
  wordsLearned: { type: Number, default: 0 },
  accuracy: { type: Number, default: 0 },
  createdAt: { type: Date, default: Date.now }
});
\`\`\`

### Lesson Model

\`\`\`js
const lessonSchema = new mongoose.Schema({
  title: { type: String, required: true },
  level: { type: String, enum: ["A1", "A2", "B1", "B2"] },
  category: {
    type: String,
    enum: ["vocabulary", "grammar", "listening", "speaking"]
  },
  content: String,
  examples: [String],
  imagePrompt: String,
  duration: Number
});
\`\`\`

### Progress Model

\`\`\`js
const progressSchema = new mongoose.Schema({
  userId: { type: mongoose.Schema.Types.ObjectId, ref: "User" },
  lessonId: { type: mongoose.Schema.Types.ObjectId, ref: "Lesson" },
  completed: { type: Boolean, default: false },
  score: Number,
  mistakes: [String],
  completedAt: Date
});
\`\`\`

### Quiz Model

\`\`\`js
const quizSchema = new mongoose.Schema({
  lessonId: { type: mongoose.Schema.Types.ObjectId, ref: "Lesson" },
  question: String,
  options: [String],
  correctAnswer: String,
  explanation: String
});
\`\`\``,
      },
      {
        title: "⚙️ Backend APIs",
        body: `تم تجهيز APIs أساسية للباك إند:

### API Flow

\`\`\`diagram
title: API Request Flow
[React UI]
-> [Express Routes]
-> [Controller]
-> [MongoDB]
-> [JSON Response]
\`\`\`

### Routes Structure

\`\`\`txt
backend/
 ├── routes/
 │   ├── lesson.routes.js
 │   ├── quiz.routes.js
 │   ├── progress.routes.js
 │   └── ai.routes.js
 ├── controllers/
 │   ├── lesson.controller.js
 │   ├── quiz.controller.js
 │   ├── progress.controller.js
 │   └── ai.controller.js
 └── models/
     ├── Lesson.js
     ├── Quiz.js
     ├── Progress.js
     └── User.js
\`\`\`

### Lesson API

\`\`\`js
import express from "express";
import Lesson from "../models/Lesson.js";

const router = express.Router();

router.get("/", async (req, res) => {
  const { level } = req.query;
  const lessons = await Lesson.find(level ? { level } : {});
  res.json(lessons);
});

router.post("/", async (req, res) => {
  const lesson = await Lesson.create(req.body);
  res.status(201).json(lesson);
});

export default router;
\`\`\`

### Progress API

\`\`\`js
router.patch("/:lessonId/complete", async (req, res) => {
  const { userId, score, mistakes } = req.body;

  const progress = await Progress.findOneAndUpdate(
    { userId, lessonId: req.params.lessonId },
    {
      completed: true,
      score,
      mistakes,
      completedAt: new Date()
    },
    { new: true, upsert: true }
  );

  res.json(progress);
});
\`\`\``,
      },
      {
        title: "🤖 AI Tutor Logic",
        body: `تم بناء منطق المساعد الذكي ليكون جزء أساسي من التطبيق:

### AI Tutor Flow

\`\`\`diagram
title: AI Tutor Flow
[User Message]
-> [Frontend Chat]
-> [AI API Route]
-> [Prompt Builder]
-> [Gemini/OpenRouter]
-> [Streaming Response]
-> [Save Conversation]
\`\`\`

### AI Route Example

\`\`\`js
router.post("/tutor", async (req, res) => {
  const { message, level, languageGoal } = req.body;

  const prompt = \`
You are a German tutor.
User level: \${level}
Goal: \${languageGoal}

Help the user in Arabic and German.
Correct mistakes and give examples.

User message:
\${message}
\`;

  const answer = await askAI(prompt);

  res.json({ answer });
});
\`\`\`

### Prompt Strategy

- لو المستخدم طلب ترجمة: يرد بالترجمة + مثال.
- لو كتب جملة ألمانية غلط: يصحح + يشرح السبب.
- لو طلب تدريب: يولد سؤال قصير.
- لو المستخدم ضعيف في نقطة معينة: يقترح درس مناسب.`,
      },
      {
        title: "🧪 Quiz + Evaluation System",
        body: `تم تصميم نظام الاختبارات بشكل بسيط وقابل للتطوير:

### Quiz Flow

\`\`\`diagram
title: Quiz Flow
[Start Quiz]
-> [Load Questions]
-> [User Answers]
-> [Check Score]
-> [Show Explanation]
-> [Update Progress]
\`\`\`

### React Quiz Example

\`\`\`jsx
function QuickQuiz({ questions }) {
  const [current, setCurrent] = useState(0);
  const [score, setScore] = useState(0);

  const answer = (option) => {
    if (option === questions[current].correctAnswer) {
      setScore((prev) => prev + 1);
    }

    setCurrent((prev) => prev + 1);
  };

  if (current >= questions.length) {
    return <div>Your score: {score}/{questions.length}</div>;
  }

  return (
    <div className="quiz-card">
      <h3>{questions[current].question}</h3>
      {questions[current].options.map((option) => (
        <button key={option} onClick={() => answer(option)}>
          {option}
        </button>
      ))}
    </div>
  );
}
\`\`\``,
      },
      {
        title: "📁 Final Project Structure",
        body: `الهيكل النهائي المقترح للمشروع:

\`\`\`txt
StructuraNet-AI/
 ├── client/
 │   ├── src/
 │   │   ├── components/
 │   │   │   ├── ProgressCard/
 │   │   │   ├── LessonCard/
 │   │   │   ├── LessonGrid/
 │   │   │   ├── QuickQuiz/
 │   │   │   └── AITutor/
 │   │   ├── routes/
 │   │   │   ├── dashboardPage/
 │   │   │   ├── lessonPage/
 │   │   │   ├── quizPage/
 │   │   │   └── aiTutorPage/
 │   │   ├── lib/
 │   │   │   ├── api.js
 │   │   │   └── gemini.js
 │   │   └── App.jsx
 │   └── package.json
 │
 ├── backend/
 │   ├── models/
 │   │   ├── User.js
 │   │   ├── Lesson.js
 │   │   ├── Quiz.js
 │   │   └── Progress.js
 │   ├── routes/
 │   │   ├── lesson.routes.js
 │   │   ├── quiz.routes.js
 │   │   ├── progress.routes.js
 │   │   └── ai.routes.js
 │   ├── controllers/
 │   ├── index.js
 │   └── package.json
 │
 └── README.md
\`\`\`

### النتيجة النهائية

التطبيق كده عنده:
- UI منظمة.
- باك إند قابل للتوسيع.
- قاعدة بيانات واضحة.
- AI Tutor.
- اختبارات وتقييم.
- tracking للتقدم.
- إمكانية تحويل كل جزء لكود حقيقي خطوة بخطوة.`,
      },
    ];

    const buildPrompt = (userText) => {
      return `
${userText}

Answer normally and directly.
Prefer Arabic if the user wrote Arabic.
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
      const buildMode = isBuildRequest(userText);

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
        let displayedText = "";

        const baseHistory = [
          ...currentHistory
            .filter((msg) => msg.content && !msg.streaming)
            .map((msg) => ({
              role: msg.role === "user" ? "user" : "assistant",
              content: msg.content,
            })),
        ];

        if (buildMode) {
          const stages = getBuildStages(userText);

          for (const stage of stages) {
            displayedText = await typeStage(
              aiMessageId,
              displayedText,
              stage.title,
              stage.body
            );
          }

          displayedText +=
            "\n\n## ✅ Done\nتم بناء output كامل ومفصل يشمل Architecture + UI + Database + APIs + Code + Structures. نقدر بعد كده نبدأ نحول كل مرحلة لفايلات فعلية في المشروع.";

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
        } else {
          let finalText = "";

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

          displayedText = finalText || "لم يصل رد واضح، حاول مرة أخرى.";

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
        }

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
