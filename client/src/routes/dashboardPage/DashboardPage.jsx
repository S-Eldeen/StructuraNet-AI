import "./dashboardPage.css";
import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { API_BASE_URL } from "../../config";

const DashboardPage = () => {
  const [text,        setText]        = useState("");
  const [loading,     setLoading]     = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [greeting,    setGreeting]    = useState("");

  const navigate = useNavigate();

  useEffect(() => {
    // FIX: localStorage.getItem("user") can return null → JSON.parse(null) crashes.
    // Read the username directly from the JWT token payload instead — always available.
    let username = "User";
    try {
      const token = localStorage.getItem("token");
      if (token) {
        const payload = JSON.parse(atob(token.split(".")[1]));
        username = payload.username || payload.email || "User";
      }
    } catch {
      username = "User";
    }

    const hasVisited = localStorage.getItem("hasVisitedStructraNet");
    if (!hasVisited) {
      setGreeting(`👋 Hello, ${username}! Welcome to StructraNet AI`);
      localStorage.setItem("hasVisitedStructraNet", "true");
    } else {
      setGreeting(`👋 Welcome back, ${username}!`);
    }
  }, []);

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
      setText(prev => prev + (prev ? " " : "") + e.results[0][0].transcript);
      setIsListening(false);
    };
    recognition.onerror = () => setIsListening(false);
    recognition.onend   = () => setIsListening(false);
    recognition.start();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading || !text.trim()) return;

    const token = localStorage.getItem("token");
    if (!token) return navigate("/sign-in");

    setLoading(true);
    try {
      // 1. Create the chat (saves the first user message)
      const res = await fetch(`${API_BASE_URL}/api/chats`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text, images: [] }),
      });

      // Handle expired token
      if (res.status === 401) {
        localStorage.removeItem("token");
        return navigate("/sign-in");
      }
      if (!res.ok) throw new Error("Failed to create chat");

      const chat = await res.json();

      // Notify sidebar to refresh
      window.dispatchEvent(new CustomEvent("chat-created"));

      // 2. Navigate immediately — ChatPage auto-triggers the AI on load
      // No more 5-minute frozen screen waiting for askGemini()
      navigate(`/dashboard/chats/${chat._id}`);

    } catch (err) {
      console.error("Create chat error:", err);
      alert("Failed to create chat. Make sure the backend is running.");
      setLoading(false);
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
            <input
              type="text"
              placeholder={loading ? "Creating chat..." : "Ask me anything ..."}
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={loading}
            />

            <button
              type="button"
              className={`mic-btn ${isListening ? "listening" : ""}`}
              onClick={startListening}
              disabled={loading}
              title="إدخال صوتي"
            >
              <img src="/microphone.png" alt="mic" className="mic-icon" />
            </button>

            <button type="submit" disabled={loading || !text.trim()}>
              <img src="/arrow.png" alt="send" className="send-icon" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default DashboardPage;
