import "./dashboardPage.css";
import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import Upload from "../../components/upload/Upload";
import { API_BASE_URL } from "../../config";

const DashboardPage = () => {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [images, setImages] = useState([]);
  const [isListening, setIsListening] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [greeting, setGreeting] = useState("");

  const navigate = useNavigate();

  useEffect(() => {
    const userData = JSON.parse(localStorage.getItem("user"));
    const username = userData?.username || "User";
    const hasVisited = localStorage.getItem("hasVisitedStructraNet");
    if (!hasVisited) {
      setGreeting(`👋 Hello, ${username}! Welcome to StructraNet AI`);
      localStorage.setItem("hasVisitedStructraNet", "true");
    } else {
      setGreeting(`👋 Welcome back, ${username}!`);
    }
  }, []);

  const handleGenerateGNS3 = async () => {
    if (!text.trim()) {
      alert("Please enter a network description first.");
      return;
    }
    setGenerating(true);
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_BASE_URL}/api/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ prompt: text }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Generation failed");
      if (data.success && data.downloadUrl) {
        window.open(`${API_BASE_URL}${data.downloadUrl}`, "_blank");
      } else {
        alert("Failed to generate: " + (data.error || "Unknown error"));
      }
    } catch (err) {
      console.error(err);
      alert("Error generating GNS3 project: " + err.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleUploadStart = (file) => {
    const previewUrl = URL.createObjectURL(file);
    setImages((prev) => [
      ...prev,
      { file, filePath: null, progress: 0, previewUrl },
    ]);
  };

  const handleUploadProgress = (percent) => {
    setImages((prev) => {
      const lastIndex = prev.length - 1;
      if (lastIndex < 0) return prev;
      const last = prev[lastIndex];
      if (last.filePath) return prev;
      const updated = [...prev];
      updated[lastIndex] = { ...last, progress: percent };
      return updated;
    });
  };

  const handleUploadSuccess = (filePath) => {
    setImages((prev) => {
      const lastIndex = prev.length - 1;
      if (lastIndex < 0) return prev;
      const updated = [...prev];
      updated[lastIndex] = { ...updated[lastIndex], filePath, progress: 100 };
      return updated;
    });
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
    recognition.onerror = () => setIsListening(false);
    recognition.onend = () => setIsListening(false);
    recognition.start();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;
    const completedImages = images
      .filter((img) => img.filePath)
      .map((img) => img.filePath);
    if (!text.trim() && completedImages.length === 0) return;
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      if (!token) return navigate("/sign-in");
      const createResponse = await fetch(`${API_BASE_URL}/api/chats`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ text, images: completedImages }),
      });
      const chat = await createResponse.json();
      window.dispatchEvent(new CustomEvent("chat-created"));
      // ✅ تم إزالة استدعاء askGemini - المستخدم سيرسل الرسالة في صفحة الشات
      navigate(`/dashboard/chats/${chat._id}`);
    } catch (error) {
      console.error(error);
      alert("Failed to create chat");
    } finally {
      setLoading(false);
      setText("");
      setImages([]);
    }
  };

  return (
    <div className="dashboardPage">
      <div className="texts">
        <div className="logo">
          <img src="/logo.png" alt="" />
          <h1>Structranet AI</h1>
        </div>

        <h2 className="greeting">{greeting}</h2>

        <div className="options">
          <div className="option">
            <img src="/chat.png" alt="" />
            <span>Create a New Chat</span>
          </div>
          <div className="option">
            <img src="/image.png" alt="" />
            <span>Analyze my Design</span>
          </div>
        </div>
      </div>

      <div className="formContainer">
        <form onSubmit={handleSubmit}>
          <div className="input-row">
            <Upload
              onStart={handleUploadStart}
              onProgress={handleUploadProgress}
              onSuccess={handleUploadSuccess}
            />

            <input
              type="text"
              placeholder={loading ? "Thinking..." : "Ask me anything ..."}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />

            <button
              type="button"
              className={`mic-btn ${isListening ? "listening" : ""}`}
              onClick={startListening}
            >
              <img src="/microphone.png" alt="mic" className="mic-icon" />
            </button>

            <button type="submit">
              <img src="/arrow.png" alt="send" className="send-icon" />
            </button>

            <button
              type="button"
              onClick={handleGenerateGNS3}
              disabled={generating || loading}
              style={{ marginLeft: "8px", background: "#10a37f", color: "#fff", border: "none", borderRadius: "8px", padding: "8px 14px", cursor: "pointer", opacity: (generating || loading) ? 0.6 : 1 }}
            >
              {generating ? "⏳ Generating..." : "🚀 Generate GNS3"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default DashboardPage;