import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import "./chatpage.css";
import NewPrompt from "../../components/newPrompt/NewPrompt";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const Chatpage = () => {
  const { id: chatId } = useParams();
  const navigate = useNavigate();

  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isTyping, setIsTyping] = useState(false);

  const endRef = useRef(null);
  const getToken = () => localStorage.getItem("token");

  const getImageSrc = (img) => {
    if (!img) return "";

    if (typeof img === "string") return img;

    if (img.data && img.mimeType) {
      return `data:${img.mimeType};base64,${img.data}`;
    }

    return "";
  };

  useEffect(() => {
    const fetchChat = async () => {
      const token = getToken();
      if (!token) return navigate("/sign-in");

      try {
        const res = await fetch(`http://localhost:3000/api/chats/${chatId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        const data = await res.json();
        setMessages(data.messages || []);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchChat();
  }, [chatId, navigate]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const addMessage = async (msg, isUpdate = false) => {
    const token = getToken();
    if (!token) return navigate("/sign-in");

    if (isUpdate && msg.id) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msg.id
            ? { ...m, content: msg.content, streaming: msg.streaming }
            : m
        )
      );
      return;
    }

    setMessages((prev) => [...prev, msg]);
  };

  if (loading) return <div className="sn-loading">Loading...</div>;

  return (
    <div className="sn-chat-page">
      <div className="sn-bg-title">StructraNet AI</div>

      <div className="sn-messages-area">
        <div className="sn-messages-inner">
          {messages.map((msg, index) => (
            <div
              key={msg.id || msg._id || index}
              className={`sn-row ${
                msg.role === "user" ? "sn-row-user" : "sn-row-ai"
              }`}
            >
              <div
                className={`sn-bubble ${
                  msg.role === "user" ? "sn-bubble-user" : "sn-bubble-ai"
                }`}
              >
                {msg.images?.length > 0 && (
                  <div className="sn-message-images">
                    {msg.images.map((img, i) => {
                      const src = getImageSrc(img);
                      if (!src) return null;

                      return (
                        <img
                          key={i}
                          src={src}
                          alt="uploaded"
                          className="sn-message-image"
                        />
                      );
                    })}
                  </div>
                )}

                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.content || ""}
                </ReactMarkdown>
              </div>
            </div>
          ))}

          {isTyping && (
            <div className="sn-row sn-row-ai">
              <div className="sn-bubble sn-bubble-ai">Typing...</div>
            </div>
          )}

          <div ref={endRef} />
        </div>
      </div>

      <div className="sn-input-area">
        <NewPrompt
          addMessage={addMessage}
          setIsTyping={setIsTyping}
          chatId={chatId}
          history={messages}
        />
      </div>
    </div>
  );
};

export default Chatpage;