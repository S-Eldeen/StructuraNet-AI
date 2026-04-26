import "./chatList.css";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
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
    <line x1="21.8" y1="16.2" x2="28.5" y2="13.5" stroke="#4f8ef7" strokeWidth="1.2" strokeOpacity="0.6" />
    <line x1="14.2" y1="16.2" x2="7.5" y2="13.5" stroke="#4f8ef7" strokeWidth="1.2" strokeOpacity="0.6" />
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

const ChatItem = ({ chat, onStar, onRename, onDelete }) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [newTitle, setNewTitle] = useState(chat.title);
  const menuRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return;

    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  useEffect(() => {
    if (renaming && inputRef.current) {
      inputRef.current.focus();
    }
  }, [renaming]);

  const submitRename = (e) => {
    e?.preventDefault();

    if (newTitle.trim() && newTitle.trim() !== chat.title) {
      onRename(chat._id, newTitle.trim());
    }

    setRenaming(false);
  };

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
        <span className="chat-title">{chat.title}</span>
      </Link>

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
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill={chat.starred ? "#f5c842" : "none"}
                stroke={chat.starred ? "#f5c842" : "currentColor"}
                strokeWidth="2"
              >
                <polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26" />
              </svg>
              <span>{chat.starred ? "Unstar" : "Star"}</span>
            </button>

            <button
              className="dropdown-item"
              onClick={() => {
                setRenaming(true);
                setMenuOpen(false);
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
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
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <polyline points="3,6 5,6 21,6" />
                <path d="M19,6l-1,14a2,2,0,0,1-2,2H8a2,2,0,0,1-2-2L5,6" />
                <path d="M10,11v6M14,11v6" />
                <path d="M9,6V4a1,1,0,0,1,1-1h4a1,1,0,0,1,1,1v2" />
              </svg>
              <span>Delete</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

const ChatList = () => {
  const { getToken, isLoaded } = useAuth();
  const [chats, setChats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const [plan, setPlan] = useState(localStorage.getItem("userPlan"));
  const navigate = useNavigate();

  const fetchChats = useCallback(async () => {
    if (!isLoaded) return;

    try {
      const token = await getToken({ skipCache: true });
      if (!token) return;

      const res = await fetch("http://localhost:3000/api/userchats", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      setChats(data.chats || []);
    } catch (err) {
      console.error("Error fetching chats:", err);
    } finally {
      setLoading(false);
    }
  }, [getToken, isLoaded]);

  useEffect(() => {
    fetchChats();
    window.addEventListener("chat-created", fetchChats);

    return () => {
      window.removeEventListener("chat-created", fetchChats);
    };
  }, [fetchChats]);

  useEffect(() => {
    const updatePlan = () => {
      setPlan(localStorage.getItem("userPlan"));
    };

    updatePlan();
    window.addEventListener("plan-changed", updatePlan);

    return () => {
      window.removeEventListener("plan-changed", updatePlan);
    };
  }, []);

  const handleStar = async (chatId, starred) => {
    setChats((prev) =>
      prev.map((c) => (c._id === chatId ? { ...c, starred } : c))
    );

    try {
      const token = await getToken({ skipCache: true });

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
    setChats((prev) =>
      prev.map((c) => (c._id === chatId ? { ...c, title } : c))
    );

    try {
      const token = await getToken({ skipCache: true });

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
    setChats((prev) => prev.filter((c) => c._id !== chatId));

    try {
      const token = await getToken({ skipCache: true });

      await fetch(`http://localhost:3000/api/userchats/${chatId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (window.location.pathname.includes(chatId)) {
        navigate("/dashboard");
      }
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
    <div className={`chatList ${collapsed ? "collapsed" : ""}`}>
      <div className="chatList-header">
        {!collapsed && (
          <Link to="/" className="chatList-brand">
            <NetworkIcon />
            <span className="brand-name">Structranet</span>
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
          <Link to="/about">Explore Structranet AI</Link>
          <Link to="/">Contact</Link>

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
                <span className="plan-title">Upgrade to Structranet Pro</span>
                <span className="subtext">Unlimited designs & priority support</span>
              </div>
            </Link>
          )}
        </>
      )}
    </div>
  );
};

export default ChatList;