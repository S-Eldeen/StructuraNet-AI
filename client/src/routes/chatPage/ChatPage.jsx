import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import "./chatpage.css";
import NewPrompt from "../../components/newPrompt/NewPrompt";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { askGeminiStream } from "../../lib/gemini";

// ── Action Buttons ────────────────────────────────────────────────────────────
const MessageActions = ({ msg, msgIndex, onRegenerate, isAi }) => {
  const [copied, setCopied] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [liked, setLiked] = useState(false);
  const [disliked, setDisliked] = useState(false);
  const [showMore, setShowMore] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopyLink = () => {
    const url = `${window.location.href.split("#")[0]}#msg-${msgIndex}`;
    navigator.clipboard.writeText(url);
    setLinkCopied(true);
    setShowMore(false);
    setTimeout(() => setLinkCopied(false), 2000);
  };

  const handleLike = () => { setLiked((p) => !p); if (disliked) setDisliked(false); };
  const handleDislike = () => { setDisliked((p) => !p); if (liked) setLiked(false); };

  return (
    <div className={`sn-msg-actions ${isAi ? "sn-msg-actions-ai" : "sn-msg-actions-user"}`}>
      <div className="sn-action-wrapper">
        <button
          className={`sn-action-btn ${linkCopied ? "sn-action-active" : ""}`}
          onClick={() => setShowMore((p) => !p)}
          title="More options"
        >
          {linkCopied ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width="15" height="15">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="currentColor" width="15" height="15">
              <circle cx="5" cy="12" r="2" />
              <circle cx="12" cy="12" r="2" />
              <circle cx="19" cy="12" r="2" />
            </svg>
          )}
        </button>

        {showMore && (
          <div className="sn-more-menu">
            <button onClick={() => { handleCopy(); setShowMore(false); }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="13" height="13">
                <rect x="9" y="9" width="13" height="13" rx="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              Copy text
            </button>
            <button onClick={handleCopyLink}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="13" height="13">
                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
              </svg>
              Copy link
            </button>
          </div>
        )}
      </div>

      <button className={`sn-action-btn ${copied ? "sn-action-active" : ""}`} onClick={handleCopy} title={copied ? "Copied!" : "Copy"}>
        {copied ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width="15" height="15"><polyline points="20 6 9 17 4 12" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="15" height="15">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
        )}
      </button>

      <button className={`sn-action-btn ${liked ? "sn-action-liked" : ""}`} onClick={handleLike} title="Like">
        <svg viewBox="0 0 24 24" fill={liked ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" width="15" height="15">
          <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3z" />
          <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
        </svg>
      </button>

      <button className={`sn-action-btn ${disliked ? "sn-action-disliked" : ""}`} onClick={handleDislike} title="Dislike">
        <svg viewBox="0 0 24 24" fill={disliked ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" width="15" height="15">
          <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z" />
          <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
        </svg>
      </button>

      {isAi && onRegenerate && (
        <button className="sn-action-btn" onClick={() => onRegenerate(msgIndex)} title="Regenerate">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="15" height="15">
            <polyline points="1 4 1 10 7 10" />
            <path d="M3.51 15a9 9 0 1 0 .49-4.95" />
          </svg>
        </button>
      )}
    </div>
  );
};

// ── Chat Header with editable title ──────────────────────────────────────────
const ChatHeader = ({ chatId, initialTitle }) => {
  const [title, setTitle] = useState(initialTitle || "");
  const [editing, setEditing] = useState(false);
  const [input, setInput] = useState(initialTitle || "");
  const inputRef = useRef(null);

  useEffect(() => {
    setTitle(initialTitle || "");
    setInput(initialTitle || "");
  }, [initialTitle]);

  useEffect(() => {
    if (editing && inputRef.current) inputRef.current.focus();
  }, [editing]);

  const handleSubmit = async (e) => {
    e?.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || trimmed === title) {
      setEditing(false);
      return;
    }

    const oldTitle = title;
    setTitle(trimmed);
    setEditing(false);

    try {
      const token = localStorage.getItem("token");
      await fetch(`http://localhost:3000/api/userchats/${chatId}/rename`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ title: trimmed }),
      });
      // إرسال حدث يحتوي على chatId والعنوان الجديد
      window.dispatchEvent(new CustomEvent("chat-renamed", {
        detail: { chatId, newTitle: trimmed }
      }));
    } catch (err) {
      console.error("Rename error:", err);
      setTitle(oldTitle);
      setInput(oldTitle);
    }
  };

  if (!title) return null;

  return (
    <div className="sn-chat-header">
      {editing ? (
        <form className="sn-title-form" onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            className="sn-title-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onBlur={handleSubmit}
            onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
          />
        </form>
      ) : (
        <button className="sn-title-btn" onClick={() => setEditing(true)} title="Click to rename">
          <span className="sn-title-text">{title}</span>
          <svg className="sn-title-edit-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
        </button>
      )}
    </div>
  );
};

// ── Main ChatPage ─────────────────────────────────────────────────────────────
const Chatpage = () => {
  const { id: chatId } = useParams();
  const navigate = useNavigate();

  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isTyping, setIsTyping] = useState(false);
  const [chatTitle, setChatTitle] = useState("");

  const endRef = useRef(null);
  const newPromptRef = useRef(null);
  const messagesRef = useRef([]);

  const getToken = () => localStorage.getItem("token");

  const getImageSrc = (img) => {
    if (!img) return "";
    if (typeof img === "string") return img;
    if (img.data && img.mimeType) return `data:${img.mimeType};base64,${img.data}`;
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
        const title = data.title || data.messages?.[0]?.content?.substring(0, 40) || "Chat";
        setChatTitle(title);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchChat();
  }, [chatId, navigate]);

  useEffect(() => {
    messagesRef.current = messages;
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const addMessage = (msg, isUpdate = false) => {
    const token = getToken();
    if (!token) return navigate("/sign-in");
    if (isUpdate && msg.id) {
      setMessages((prev) => prev.map((m) => m.id === msg.id ? { ...m, content: msg.content, streaming: msg.streaming } : m));
      return;
    }
    setMessages((prev) => [...prev, msg]);
  };

  const handleRegenerate = async (msgIndex) => {
    const current = messagesRef.current;
    const clickedMsg = current[msgIndex];
    const lastUserMsg = [...current.slice(0, msgIndex + 1)].reverse().find((m) => m.role === "user");
    if (!lastUserMsg) return;

    const cutIndex = clickedMsg.role === "user" ? msgIndex + 1 : msgIndex;
    const historyUpToAi = current.slice(0, cutIndex);
    setMessages(historyUpToAi);
    setIsTyping(true);

    const aiMessageId = Date.now() + Math.random();
    setMessages((prev) => [...prev, { role: "assistant", content: "", id: aiMessageId, streaming: true, images: [] }]);

    try {
      let accumulatedText = "";
      const conversation = historyUpToAi
        .filter((m) => m.content && !m.streaming)
        .map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.content }));

      await askGeminiStream(conversation, lastUserMsg.images?.map((img) => img.data) || [], (partialText) => {
        accumulatedText = partialText;
        setMessages((prev) => prev.map((m) => m.id === aiMessageId ? { ...m, content: accumulatedText, streaming: true } : m));
      });

      setMessages((prev) => prev.map((m) => m.id === aiMessageId ? { ...m, content: accumulatedText, streaming: false } : m));

      const token = getToken();
      if (chatId && token) {
        await fetch(`http://localhost:3000/api/chats/${chatId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ messages: [{ role: "assistant", content: accumulatedText, images: [] }] }),
        });
      }
    } catch (error) {
      console.error("Regenerate error:", error);
      setMessages((prev) => prev.map((m) => m.id === aiMessageId ? { ...m, content: "عذراً، حدث خطأ. حاول مرة أخرى.", streaming: false } : m));
    } finally {
      setIsTyping(false);
    }
  };

  const lastAiIndex = messages.map((m, i) => ({ ...m, i })).filter((m) => m.role === "assistant").at(-1)?.i;

  if (loading) return <div className="sn-loading">Loading...</div>;

  return (
    <div className="sn-chat-page">
      <div className="sn-bg-title">StructraNet AI</div>

      <ChatHeader chatId={chatId} initialTitle={chatTitle} />

      <div className="sn-messages-area">
        <div className="sn-messages-inner">
          {messages.map((msg, index) => {
            const isAi = msg.role === "assistant";
            const isStreaming = msg.streaming;
            const msgId = msg.id || msg._id || index;

            return (
              <div
                key={msgId}
                id={`msg-${index}`}
                className={`sn-msg-wrapper ${isAi ? "sn-msg-wrapper-ai" : "sn-msg-wrapper-user"}`}
              >
                <div className={`sn-row ${isAi ? "sn-row-ai" : "sn-row-user"}`}>
                  <div className={`sn-bubble ${isAi ? "sn-bubble-ai" : "sn-bubble-user"}`}>
                    {msg.images?.length > 0 && (
                      <div className="sn-message-images">
                        {msg.images.map((img, i) => {
                          const src = getImageSrc(img);
                          if (!src) return null;
                          return <img key={i} src={src} alt="uploaded" className="sn-message-image" />;
                        })}
                      </div>
                    )}
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        code({ node, inline, className, children, ...props }) {
                          const match = /language-(\w+)/.exec(className || '');
                          const codeText = String(children).replace(/\n$/, '');
                          if (!inline && match) {
                            return (
                              <div className="sn-code-block">
                                <div className="sn-code-header">
                                  <span className="sn-code-lang">{match[1]}</span>
                                  <button
                                    className="sn-copy-code-btn"
                                    onClick={() => navigator.clipboard.writeText(codeText)}
                                    title="Copy code"
                                  >
                                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                                    </svg>
                                    نسخ
                                  </button>
                                </div>
                                <SyntaxHighlighter
                                  style={vscDarkPlus}
                                  language={match[1]}
                                  PreTag="div"
                                  showLineNumbers
                                  {...props}
                                >
                                  {codeText}
                                </SyntaxHighlighter>
                              </div>
                            );
                          }
                          return <code className={`sn-inline-code ${className || ''}`} {...props}>{children}</code>;
                        }
                      }}
                    >
                      {msg.content || ""}
                    </ReactMarkdown>
                  </div>
                </div>

                {!isStreaming && (
                  <MessageActions msg={msg} msgIndex={index} isAi={isAi} onRegenerate={handleRegenerate} />
                )}
              </div>
            );
          })}

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
          ref={newPromptRef}
          addMessage={addMessage}
          setIsTyping={setIsTyping}
          chatId={chatId}
          history={messages}
          onRegenerate={() => lastAiIndex !== undefined && handleRegenerate(lastAiIndex)}
        />
      </div>
    </div>
  );
};

export default Chatpage;