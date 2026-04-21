import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import './chatpage.css';
import NewPrompt from '../../components/newPrompt/NewPrompt';
import ChatList from '../../components/chatList/ChatList';
import Markdown from 'react-markdown';
import { useAuth } from '@clerk/clerk-react';

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
        const token = await getToken();
        const response = await fetch(`http://localhost:3000/api/chats/${chatId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error('Failed to fetch chat');
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
      const token = await getToken();
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
      setMessages(prev => prev.map(msg =>
        msg.id === message.id ? { ...msg, content: message.content, streaming: message.streaming } : msg
      ));
    } else {
      const newMsg = { ...message, id: message.id || Date.now() + Math.random() };
      setMessages(prev => [...prev, newMsg]);
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

  if (loading) return (
    <div className="global-logo-loader">
      <div className="logo-spinner-wrapper">
        <div className="spinner-ring"></div>
        <img src="/logo.png" alt="Loading" className="spinner-logo" />
      </div>
    </div>
  );

  return (
    <div className="chatpage">
      <div className="content">
        <div className="wrapper" ref={wrapperRef}>
          <div className="chat">
            {messages.map((msg, index) => (
              <div key={msg.id || index} className={`message ${msg.role} ${msg.streaming ? 'streaming' : ''}`}>
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
            ))}

            {isTyping && (
              <div className="message ai typing-indicator" style={{ backgroundColor: 'transparent', padding: '0', boxShadow: 'none' }}>
                <div className="logo-spinner-wrapper" style={{ width: '30px', height: '30px' }}>
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