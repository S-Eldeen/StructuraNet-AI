import "./chatList.css";
import { Link } from "react-router-dom";
import { useAuth } from '@clerk/clerk-react';
import { useEffect, useState, useCallback } from 'react';

const ChatList = () => {
  const { getToken, isLoaded } = useAuth();
  const [chats, setChats] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchChats = useCallback(async () => {
    if (!isLoaded) return;
    try {
      const token = await getToken();
      if (!token) return;
      const response = await fetch("http://localhost:3000/api/userchats", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      setChats(data.chats || []);
    } catch (error) {
      console.error("❌ Error fetching chats:", error);
    } finally {
      setLoading(false);
    }
  }, [getToken, isLoaded]);

  useEffect(() => {
    fetchChats();
    const handleChatCreated = () => fetchChats();
    window.addEventListener('chat-created', handleChatCreated);
    return () => window.removeEventListener('chat-created', handleChatCreated);
  }, [fetchChats]);

  return (
    <div className="chatList">
      <span className="title">DASHBOARD</span>
      <Link to="/dashboard">Create a new Chat</Link>
      <Link to="/">Explore Structranet AI</Link>
      <Link to="/">Contact</Link>
      <hr />
      <span className="title">RECENT CHATS</span>
      <div className="list">
        {loading ? (
          <div className="loading-message">Loading...</div>
        ) : chats.length === 0 ? (
          <div className="no-chats">No chats yet</div>
        ) : (
          chats.map(chat => (
            <Link key={chat._id} to={`/dashboard/chats/${chat._id}`} className="chat-item">
              {chat.title}
            </Link>
          ))
        )}
      </div>
      <hr />
      <Link to="/" className="upgrade">
        <img src="/logo.png" alt="Structranet Logo" />
        <div className="texts">
          <span>Upgrade to Structranet Pro</span>
          <span className="subtext">Get unlimited Network Designs & Priority support</span>
        </div>
      </Link>
    </div>
  );
};

export default ChatList;