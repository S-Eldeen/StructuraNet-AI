import "./chatList.css";
import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState, useCallback, useRef } from "react";

/* ── Icons ── */
const NetworkIcon = () => (
  <svg width="20" height="20" viewBox="0 0 36 36" fill="none">
    <circle cx="18" cy="18" r="4" fill="#4f8ef7" />
    <circle cx="18" cy="5" r="3" fill="#7eb3ff" />
    <circle cx="6" cy="28" r="3" fill="#7eb3ff" />
    <circle cx="30" cy="28" r="3" fill="#7eb3ff" />
    <circle cx="31" cy="12" r="2.5" fill="#a8ccff" />
    <circle cx="5" cy="12" r="2.5" fill="#a8ccff" />
    <line x1="18" y1="14" x2="18" y2="8" stroke="#4f8ef7" strokeWidth="1.5" strokeOpacity="0.8" />
    <line x1="14.5" y1="21" x2="7.5" y2="26.5" stroke="#4f8ef7" strokeWidth="1.5" strokeOpacity="0.8" />
    <line x1="21.5" y1="21" x2="28.5" y2="26.5" stroke="#4f8ef7" strokeWidth="1.5" strokeOpacity="0.8" />
  </svg>
);

const ToggleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" strokeWidth="1.8" />
    <line x1="9" y1="3" x2="9" y2="21" stroke="currentColor" strokeWidth="1.8" />
  </svg>
);

const NewChatIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
    <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const DotsIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
    <circle cx="5" cy="12" r="2" />
    <circle cx="12" cy="12" r="2" />
    <circle cx="19" cy="12" r="2" />
  </svg>
);

const ShareIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="18" cy="5" r="3" />
    <circle cx="6" cy="12" r="3" />
    <circle cx="18" cy="19" r="3" />
    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
    <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
  </svg>
);

const formatDate = (dateStr) => {
  if (!dateStr) return null;
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now - date;
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;

  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

const getLocalToken = () => localStorage.getItem("token");

const ShareModal = ({ chatId, onClose }) => {
  const link = `${window.location.origin}/dashboard/chats/${chatId}`;
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(link).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="share-modal-overlay" onMouseDown={onClose}>
      <div className="share-modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="share-modal-header">
          <span className="share-modal-title">Share Chat</span>
          <button className="share-modal-close" onClick={onClose}>✕</button>
        </div>
        <p className="share-modal-desc">Anyone with this link can view this chat.</p>
        <div className="share-modal-row">
          <input className="share-modal-input" value={link} readOnly />
          <button className="share-modal-copy" onClick={handleCopy}>
            {copied ? "✓ Copied" : "Copy"}
          </button>
        </div>
      </div>
    </div>
  );
};

const ChatItem = ({ chat, onStar, onRename, onDelete, onShareClick }) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [newTitle, setNewTitle] = useState(chat.title);
  const menuRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  useEffect(() => {
    if (renaming && inputRef.current) inputRef.current.focus();
  }, [renaming]);

  const submitRename = (e) => {
    e?.preventDefault();
    if (newTitle.trim() && newTitle.trim() !== chat.title) {
      onRename(chat._id, newTitle.trim());
    }
    setRenaming(false);
  };

  const lastModified = formatDate(chat.updatedAt || chat.createdAt);

  if (renaming) {
    return (
      <form className="rename-form" onSubmit={submitRename}>
        <input
          ref={inputRef}
          className="rename-input"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          onBlur={submitRename}
          onKeyDown={(e) => e.key === "Escape" && setRenaming(false)}
        />
      </form>
    );
  }

  return (
    <div className={`chat-item-wrapper ${menuOpen ? "menu-open" : ""}`}>
      <Link to={`/dashboard/chats/${chat._id}`} className="chat-item">
        {chat.starred && <span className="star-dot">★</span>}
        <div className="chat-item-info">
          <span className="chat-title">{chat.title}</span>
          {lastModified && <span className="chat-last-modified">{lastModified}</span>}
        </div>
      </Link>

      <button
        className="share-btn"
        title="Share chat"
        onClick={(e) => {
          e.preventDefault();
          onShareClick(chat._id);
        }}
      >
        <ShareIcon />
      </button>

      <div className="chat-item-menu" ref={menuRef}>
        <button
          className="dots-btn"
          onClick={(e) => {
            e.preventDefault();
            setMenuOpen((o) => !o);
          }}
          title="More options"
        >
          <DotsIcon />
        </button>

        {menuOpen && (
          <div className="dropdown-menu">
            <button
              className="dropdown-item"
              onClick={() => {
                onStar(chat._id, !chat.starred);
                setMenuOpen(false);
              }}
            >
              <span>{chat.starred ? "Unstar" : "Star"}</span>
            </button>

            <button
              className="dropdown-item"
              onClick={() => {
                setRenaming(true);
                setMenuOpen(false);
              }}
            >
              <span>Rename</span>
            </button>

            <div className="dropdown-divider" />

            <button
              className="dropdown-item danger"
              onClick={() => {
                onDelete(chat._id);
                setMenuOpen(false);
              }}
            >
              <span>Delete</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

const ChatList = () => {
  const [chats, setChats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const [plan, setPlan] = useState(localStorage.getItem("userPlan"));
  const [shareModalChatId, setShareModalChatId] = useState(null);
  const navigate = useNavigate();

  const fetchChats = useCallback(async () => {
    const token = getLocalToken();

    if (!token) {
      setLoading(false);
      navigate("/sign-in");
      return;
    }

    try {
      const res = await fetch("http://localhost:3000/api/userchats", {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      setChats(data.chats || []);
    } catch (err) {
      console.error("Error fetching chats:", err);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    fetchChats();
    window.addEventListener("chat-created", fetchChats);
    window.addEventListener("chat-renamed", fetchChats);

    return () => {
      window.removeEventListener("chat-created", fetchChats);
      window.removeEventListener("chat-renamed", fetchChats);
    };
  }, [fetchChats]);

  useEffect(() => {
    const updatePlan = () => setPlan(localStorage.getItem("userPlan"));
    updatePlan();

    window.addEventListener("plan-changed", updatePlan);
    return () => window.removeEventListener("plan-changed", updatePlan);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/sign-in");
  };

  const handleStar = async (chatId, starred) => {
    const token = getLocalToken();
    if (!token) return navigate("/sign-in");

    setChats((prev) => prev.map((c) => (c._id === chatId ? { ...c, starred } : c)));

    try {
      await fetch(`http://localhost:3000/api/userchats/${chatId}/star`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ starred }),
      });
    } catch (err) {
      console.error("Error starring:", err);
      fetchChats();
    }
  };

  const handleRename = async (chatId, title) => {
    const token = getLocalToken();
    if (!token) return navigate("/sign-in");

    setChats((prev) => prev.map((c) => (c._id === chatId ? { ...c, title } : c)));

    try {
      await fetch(`http://localhost:3000/api/userchats/${chatId}/rename`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ title }),
      });
    } catch (err) {
      console.error("Error renaming:", err);
      fetchChats();
    }
  };

  const handleDelete = async (chatId) => {
    const token = getLocalToken();
    if (!token) return navigate("/sign-in");

    setChats((prev) => prev.filter((c) => c._id !== chatId));

    try {
      await fetch(`http://localhost:3000/api/userchats/${chatId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (window.location.pathname.includes(chatId)) navigate("/dashboard");
    } catch (err) {
      console.error("Error deleting:", err);
      fetchChats();
    }
  };

  const sortedChats = [...chats].sort((a, b) => {
    if (a.starred && !b.starred) return -1;
    if (!a.starred && b.starred) return 1;
    return new Date(b.createdAt) - new Date(a.createdAt);
  });

  return (
    <>
      {shareModalChatId && (
        <ShareModal chatId={shareModalChatId} onClose={() => setShareModalChatId(null)} />
      )}

      <div className={`chatList ${collapsed ? "collapsed" : ""}`}>
        <div className="chatList-header">
          {!collapsed && (
            <Link to="/" className="chatList-brand">
              <NetworkIcon />
              <span className="brand-name">StructraNet AI</span>
            </Link>
          )}

          <button
            className="toggle-btn"
            onClick={() => setCollapsed((c) => !c)}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <ToggleIcon />
          </button>
        </div>

        <div className={`user-profile ${collapsed ? "collapsed" : ""}`}>
          <div className="local-user-avatar">A</div>
          {!collapsed && <span className="user-name">My Account</span>}
        </div>

        {!collapsed ? (
          <Link to="/dashboard" className="new-chat-btn">
            <NewChatIcon />
            <span>New Chat</span>
          </Link>
        ) : (
          <Link to="/dashboard" className="new-chat-icon-only" title="New Chat">
            <NewChatIcon />
          </Link>
        )}

        {!collapsed && (
          <>
            <Link to="/about">Explore StructraNet AI</Link>
            <Link to="/">Contact</Link>

            <button className="logout-btn" onClick={handleLogout}>
              Sign Out
            </button>

            <hr />

            <span className="title">RECENT CHATS</span>

            <div className="list">
              {loading ? (
                <div className="loading-message">Loading...</div>
              ) : sortedChats.length === 0 ? (
                <div className="no-chats">No chats yet</div>
              ) : (
                sortedChats.map((chat) => (
                  <ChatItem
                    key={chat._id}
                    chat={chat}
                    onStar={handleStar}
                    onRename={handleRename}
                    onDelete={handleDelete}
                    onShareClick={(id) => setShareModalChatId(id)}
                  />
                ))
              )}
            </div>

            <hr />

            {plan ? (
              <div
                className="upgrade current-plan-box"
                onClick={() => navigate("/upgrade")}
                role="button"
                tabIndex={0}
              >
                <NetworkIcon />
                <div className="texts">
                  <span className="plan-title">Current Plan: {plan.toUpperCase()}</span>
                  <span className="subtext">Click to change your plan</span>
                </div>
              </div>
            ) : (
              <Link to="/upgrade" className="upgrade">
                <NetworkIcon />
                <div className="texts">
                  <span className="plan-title">Upgrade to StructraNet Pro</span>
                  <span className="subtext">Unlimited designs & priority support</span>
                </div>
              </Link>
            )}
          </>
        )}
      </div>
    </>
  );
};

export default ChatList;