import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import "./chatpage.css";
import NewPrompt from "../../components/newPrompt/NewPrompt";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { askGeminiStream } from "../../lib/gemini";
import { API_BASE_URL } from "../../config";

// ── Thinking Block ────────────────────────────────────────────────────────────
const ThinkingBlock = ({ label = "Thinking..." }) => (
  <div className="sn-claude-thinking">
    <div className="sn-claude-spinner" aria-hidden="true" />
    <span>{label}</span>
  </div>
);

// ── Diagram Renderer ──────────────────────────────────────────────────────────
const DiagramBlock = ({ value = "" }) => {
  const rawLines = value.split("\n").map((l) => l.trim()).filter(Boolean);
  const titleLine = rawLines.find((l) => l.toLowerCase().startsWith("title:"));
  const title = titleLine ? titleLine.replace(/^title:\s*/i, "") : "Architecture Diagram";
  const contentLines = rawLines.filter((l) => !l.toLowerCase().startsWith("title:"));
  const joined = contentLines.join(" ");

  let nodes = [...joined.matchAll(/\[([^\]]+)\]/g)].map((m) => m[1].trim());
  if (!nodes.length) {
    nodes = contentLines
      .flatMap((l) => l.split(/->|→|=>/g))
      .map((p) => p.replace(/^[\-\s]+|[\-\s]+$/g, "").trim())
      .filter(Boolean);
  }

  const uniqueNodes = [...new Set(nodes)].slice(0, 8);
  if (!uniqueNodes.length) return <pre className="sn-diagram-fallback">{value}</pre>;

  return (
    <div className="sn-diagram-card">
      <div className="sn-diagram-title">{title}</div>
      <div className="sn-diagram-flow">
        {uniqueNodes.map((node, i) => (
          <div className="sn-diagram-step" key={`${node}-${i}`}>
            <div className="sn-diagram-node">{node}</div>
            {i < uniqueNodes.length - 1 && <div className="sn-diagram-arrow">→</div>}
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Message Actions ───────────────────────────────────────────────────────────
const MessageActions = ({ msg, msgIndex, onRegenerate, isAi }) => {
  const [copied,   setCopied]   = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [liked,    setLiked]    = useState(false);
  const [disliked, setDisliked] = useState(false);
  const [showMore, setShowMore] = useState(false);
  const menuRef = useRef(null);

  // FIX: close dropdown on outside click
  useEffect(() => {
    if (!showMore) return;
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setShowMore(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showMore]);

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

  return (
    <div className={`sn-msg-actions ${isAi ? "sn-msg-actions-ai" : "sn-msg-actions-user"}`}>
      {/* More menu */}
      <div className="sn-action-wrapper" ref={menuRef}>
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
              <circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" />
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

      {/* Copy */}
      <button className={`sn-action-btn ${copied ? "sn-action-active" : ""}`} onClick={handleCopy} title={copied ? "Copied!" : "Copy"}>
        {copied ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" width="15" height="15"><polyline points="20 6 9 17 4 12" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="15" height="15">
            <rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
        )}
      </button>

      {/* Like */}
      <button className={`sn-action-btn ${liked ? "sn-action-liked" : ""}`} onClick={() => { setLiked((p) => !p); if (disliked) setDisliked(false); }} title="Like">
        <svg viewBox="0 0 24 24" fill={liked ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" width="15" height="15">
          <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3z" />
          <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
        </svg>
      </button>

      {/* Dislike */}
      <button className={`sn-action-btn ${disliked ? "sn-action-disliked" : ""}`} onClick={() => { setDisliked((p) => !p); if (liked) setLiked(false); }} title="Dislike">
        <svg viewBox="0 0 24 24" fill={disliked ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" width="15" height="15">
          <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z" />
          <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
        </svg>
      </button>

      {/* Regenerate */}
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

// ── Chat Header (editable title) ──────────────────────────────────────────────
const ChatHeader = ({ chatId, initialTitle }) => {
  const [title,   setTitle]   = useState(initialTitle || "");
  const [editing, setEditing] = useState(false);
  const [input,   setInput]   = useState(initialTitle || "");
  const inputRef = useRef(null);

  useEffect(() => { setTitle(initialTitle || ""); setInput(initialTitle || ""); }, [initialTitle]);
  useEffect(() => { if (editing && inputRef.current) inputRef.current.focus(); }, [editing]);

  const handleSubmit = async (e) => {
    e?.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || trimmed === title) { setEditing(false); return; }
    const old = title;
    setTitle(trimmed);
    setEditing(false);
    try {
      const token = localStorage.getItem("token");
      await fetch(`${API_BASE_URL}/api/userchats/${chatId}/rename`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ title: trimmed }),
      });
      window.dispatchEvent(new CustomEvent("chat-renamed", { detail: { chatId, newTitle: trimmed } }));
    } catch {
      setTitle(old); setInput(old);
    }
  };

  if (!title) return null;

  return (
    <div className="sn-chat-header">
      {editing ? (
        <form className="sn-title-form" onSubmit={handleSubmit}>
          <input
            ref={inputRef} className="sn-title-input" value={input}
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

// ── Markdown components config ────────────────────────────────────────────────
const makeMarkdownComponents = () => ({
  code({ node, inline, className, children, ...props }) {
    const match    = /language-(\w+)/.exec(className || "");
    const codeText = String(children).replace(/\n$/, "");
    if (!inline && match) {
      const lang = match[1].toLowerCase();
      if (["diagram", "flow", "architecture"].includes(lang))
        return <DiagramBlock value={codeText} />;
      return (
        <div className="sn-code-block">
          <div className="sn-code-header">
            <span className="sn-code-lang">{match[1]}</span>
            <button className="sn-copy-code-btn"
              onClick={() => navigator.clipboard.writeText(codeText)} title="Copy code">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              نسخ
            </button>
          </div>
          <SyntaxHighlighter style={vscDarkPlus} language={match[1]} PreTag="div" showLineNumbers {...props}>
            {codeText}
          </SyntaxHighlighter>
        </div>
      );
    }
    return <code className={`sn-inline-code ${className || ""}`} {...props}>{children}</code>;
  },
});

const markdownComponents = makeMarkdownComponents();

// ── Main ChatPage ─────────────────────────────────────────────────────────────
const Chatpage = () => {
  const { id: chatId } = useParams();
  const navigate = useNavigate();

  const [messages,  setMessages]  = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [isTyping,  setIsTyping]  = useState(false);
  const [chatTitle, setChatTitle] = useState("");

  const endRef       = useRef(null);
  const newPromptRef = useRef(null);
  const messagesRef  = useRef([]);

  const getToken = () => localStorage.getItem("token");

  const getImageSrc = (img) => {
    if (!img) return "";
    if (typeof img === "string") return img;
    if (img.data && img.mimeType) return `data:${img.mimeType};base64,${img.data}`;
    return "";
  };

  // ── addMessage ──────────────────────────────────────────────────────────────
  const addMessage = useCallback((msg, isUpdate = false) => {
    if (!getToken()) return navigate("/sign-in");
    if (isUpdate && msg.id) {
      setMessages((prev) =>
        prev.map((m) => m.id === msg.id ? { ...m, content: msg.content, streaming: msg.streaming } : m)
      );
      return;
    }
    setMessages((prev) => [...prev, msg]);
  }, [navigate]);

  // ── Fetch chat on load ──────────────────────────────────────────────────────
  useEffect(() => {
    const fetchChat = async () => {
      const token = getToken();
      if (!token) return navigate("/sign-in");

      try {
        const res = await fetch(`${API_BASE_URL}/api/chats/${chatId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        // FIX: handle expired/invalid token
        if (res.status === 401) {
          localStorage.removeItem("token");
          return navigate("/sign-in");
        }

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();
        const msgs = data.messages || [];
        setMessages(msgs);
        setChatTitle(data.title || msgs[0]?.content?.substring(0, 40) || "Chat");
      } catch (err) {
        console.error("fetchChat error:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchChat();
  }, [chatId, navigate]);

  // ── FIX: Auto-trigger AI when last message is from user (no reply yet) ──────
  // This happens when DashboardPage navigates here immediately after chat creation.
  // The user's first message is in the DB but the AI hasn't responded.
  useEffect(() => {
    if (loading) return;                                    // wait for fetch
    if (messages.length === 0) return;
    if (isTyping) return;                                   // already running

    const lastMsg = messages[messages.length - 1];
    if (lastMsg?.role !== "user") return;                   // AI already replied

    const triggerAI = async () => {
      setIsTyping(true);
      const aiId = Date.now() + Math.random();

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "", id: aiId, streaming: true, images: [] },
      ]);

      const conversation = messages
        .filter((m) => m.content && !m.streaming)
        .map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.content }));

      let finalText = "";
      try {
        await askGeminiStream(conversation, [], (partial) => {
          finalText = partial;
          setMessages((prev) =>
            prev.map((m) => m.id === aiId ? { ...m, content: partial, streaming: true } : m)
          );
        });

        setMessages((prev) =>
          prev.map((m) => m.id === aiId ? { ...m, content: finalText, streaming: false } : m)
        );

        // Save AI reply to DB
        const token = getToken();
        if (chatId && token && finalText) {
          await fetch(`${API_BASE_URL}/api/chats/${chatId}/messages`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
            body: JSON.stringify({
              messages: [{ role: "assistant", content: finalText, images: [] }],
            }),
          });
        }
      } catch (err) {
        console.error("Auto-trigger error:", err);
        setMessages((prev) =>
          prev.map((m) => m.id === aiId ? { ...m, content: "❌ حدث خطأ. حاول مرة أخرى.", streaming: false } : m)
        );
      } finally {
        setIsTyping(false);
      }
    };

    triggerAI();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]); // runs once after initial fetch completes

  // ── Auto-scroll ─────────────────────────────────────────────────────────────
  useEffect(() => {
    messagesRef.current = messages;
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Regenerate ──────────────────────────────────────────────────────────────
  const handleRegenerate = async (msgIndex) => {
    const confirmed = window.confirm(
      "Regenerating will create a new GNS3 project and may take a while. Continue?"
    );
    if (!confirmed) return;

    const current     = messagesRef.current;
    const clickedMsg  = current[msgIndex];
    const lastUserMsg = [...current.slice(0, msgIndex + 1)].reverse().find((m) => m.role === "user");
    if (!lastUserMsg) return;

    const cutIndex      = clickedMsg.role === "user" ? msgIndex + 1 : msgIndex;
    const historyUpToAi = current.slice(0, cutIndex);
    setMessages(historyUpToAi);
    setIsTyping(true);

    const aiId = Date.now() + Math.random();
    setMessages((prev) => [...prev, { role: "assistant", content: "", id: aiId, streaming: true, images: [] }]);

    try {
      let accumulated = "";
      const conversation = historyUpToAi
        .filter((m) => m.content && !m.streaming)
        .map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.content }));

      await askGeminiStream(
        conversation,
        lastUserMsg.images?.map((img) => img.data) || [],
        (partial) => {
          accumulated = partial;
          setMessages((prev) =>
            prev.map((m) => m.id === aiId ? { ...m, content: accumulated, streaming: true } : m)
          );
        }
      );

      setMessages((prev) =>
        prev.map((m) => m.id === aiId ? { ...m, content: accumulated, streaming: false } : m)
      );

      const token = getToken();
      if (chatId && token) {
        await fetch(`${API_BASE_URL}/api/chats/${chatId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ messages: [{ role: "assistant", content: accumulated, images: [] }] }),
        });
      }
    } catch (err) {
      console.error("Regenerate error:", err);
      setMessages((prev) =>
        prev.map((m) => m.id === aiId ? { ...m, content: "❌ حدث خطأ. حاول مرة أخرى.", streaming: false } : m)
      );
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
            const isAi       = msg.role === "assistant";
            const isStreaming = msg.streaming;
            const msgId      = msg.id || msg._id || index;

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
                          return src ? <img key={i} src={src} alt="uploaded" className="sn-message-image" /> : null;
                        })}
                      </div>
                    )}

                    {isAi && isStreaming && !msg.content ? (
                      <ThinkingBlock label="Thinking..." />
                    ) : (
                      <div className={`sn-response-content ${isAi ? "sn-response-content-ai" : ""} ${isStreaming ? "sn-response-streaming" : ""}`}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                          {msg.content || ""}
                        </ReactMarkdown>
                      </div>
                    )}
                  </div>
                </div>

                {!isStreaming && (
                  <MessageActions
                    msg={msg}
                    msgIndex={index}
                    isAi={isAi}
                    onRegenerate={handleRegenerate}
                  />
                )}
              </div>
            );
          })}
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