import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import './chatpage.css';
import NewPrompt from '../../components/newPrompt/NewPrompt';
import ChatList from '../../components/chatList/ChatList';
import Markdown from 'react-markdown';
import { useAuth } from '@clerk/clerk-react';

const MessageActions = ({ msg, onRegenerate }) => {
  const [copied, setCopied] = useState(false);
  const [liked, setLiked] = useState(false);
  const [disliked, setDisliked] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleLike = () => {
    setLiked((prev) => !prev);
    if (disliked) setDisliked(false);
  };

  const handleDislike = () => {
    setDisliked((prev) => !prev);
    if (liked) setLiked(false);
  };

  const handleShare = () => {
    if (navigator.share) {
      navigator.share({ text: msg.content || '' });
    } else {
      navigator.clipboard.writeText(msg.content || '');
    }
  };

  return (
    <div className={`message-actions ${msg.role}`}>
      <button className="action-btn" onClick={handleCopy} title="نسخ">
        {copied ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
        )}
      </button>

      <button className={`action-btn ${liked ? 'active-like' : ''}`} onClick={handleLike} title="إعجاب">
        <svg viewBox="0 0 24 24" fill={liked ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2">
          <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z" />
          <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
        </svg>
      </button>

      <button className={`action-btn ${disliked ? 'active-dislike' : ''}`} onClick={handleDislike} title="عدم إعجاب">
        <svg viewBox="0 0 24 24" fill={disliked ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2">
          <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z" />
          <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
        </svg>
      </button>

      <button className="action-btn" onClick={handleShare} title="مشاركة">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
          <polyline points="16 6 12 2 8 6" />
          <line x1="12" y1="2" x2="12" y2="15" />
        </svg>
      </button>

      <button className="action-btn" onClick={onRegenerate} title="إعادة التوليد">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="23 4 23 10 17 10" />
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
        </svg>
      </button>
    </div>
  );
};

const urlEndpoint = import.meta.env.VITE_IMAGE_KIT_ENDPOINT;

const Chatpage = () => {
  const { id: chatId } = useParams();
  const { getToken } = useAuth();
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const [loading, setLoading] = useState(true);

  const endRef = useRef(null);
  const wrapperRef = useRef(null);

  useEffect(() => {
    const fetchChat = async () => {
      if (!chatId) return;

      try {
        const token = await getToken({ skipCache: true });

        const response = await fetch(`http://localhost:3000/api/chats/${chatId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!response.ok) {
          throw new Error('Failed to fetch chat');
        }

        const chat = await response.json();
        setMessages(chat.messages || []);
      } catch (error) {
        console.error('Error fetching chat:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchChat();
  }, [chatId, getToken]);

  const saveMessages = async (newMessages) => {
    if (!chatId) return;

    try {
      const token = await getToken({ skipCache: true });

      await fetch(`http://localhost:3000/api/chats/${chatId}/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ messages: newMessages }),
      });
    } catch (error) {
      console.error('Error saving messages:', error);
    }
  };

  const addMessage = async (message, isUpdate = false) => {
    if (isUpdate && message.id) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === message.id
            ? { ...msg, content: message.content, streaming: message.streaming }
            : msg
        )
      );
    } else {
      const newMsg = { ...message, id: message.id || Date.now() + Math.random() };

      setMessages((prev) => [...prev, newMsg]);

      if (!message.streaming && !isUpdate) {
        await saveMessages([newMsg]);
      }
    }
  };

  const scrollToBottom = () => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    setTimeout(scrollToBottom, 100);
  }, []);

  if (loading) {
    return (
      <div className="global-logo-loader">
        <div className="logo-spinner-wrapper">
          <div className="spinner-ring"></div>
          <img src="/logo.png" alt="Loading" className="spinner-logo" />
        </div>
      </div>
    );
  }

  return (
    <div className="chatpage">
      <div className="content">
        <div className="wrapper" ref={wrapperRef}>
          <div className="chat">
            {messages.map((msg, index) => (
              <div key={msg.id || index} className="message-wrapper">
                <div
                  className={`message ${msg.role} ${msg.streaming ? 'streaming' : ''}`}
                >
                  {msg.role === 'user' && msg.images?.length > 0 && (
                    <div className="user-images">
                      {msg.images.map((img, i) => (
                        <img
                          key={i}
                          src={urlEndpoint + img}
                          alt={`صورة المستخدم ${i}`}
                          className="user-image-full"
                          onLoad={scrollToBottom}
                        />
                      ))}
                    </div>
                  )}

                  {msg.content && <Markdown>{msg.content}</Markdown>}
                </div>

                {!msg.streaming && msg.content && (
                  <MessageActions msg={msg} />
                )}
              </div>
            ))}

            {isTyping && (
              <div
                className="message ai typing-indicator"
                style={{ backgroundColor: 'transparent', padding: '0', boxShadow: 'none' }}
              >
                <div className="logo-spinner-wrapper typing-dynamic-logo">
                  <div className="spinner-ring"></div>
                  <img src="/logo.png" alt="Typing" className="spinner-logo" />
                </div>
              </div>
            )}

            <div ref={endRef} style={{ height: '1px' }}></div>
          </div>
        </div>

        <div className="prompt-container">
          <NewPrompt
            addMessage={addMessage}
            setIsTyping={setIsTyping}
            chatId={chatId}
            history={messages}
          />
        </div>
      </div>

      <div className="chatList-container">
        <ChatList />
      </div>
    </div>
  );
};

export default Chatpage;
