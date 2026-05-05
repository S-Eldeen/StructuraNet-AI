import { useState, useEffect } from 'react';
import './ChatBubble.css';

const messages = [
  "Hello, I'm Structra",
  "Your AI network design assistant",
  "How can I help you today?"
];

const ChatBubble = () => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setCurrentIndex((prev) => (prev + 1) % messages.length);
        setVisible(true);
      }, 350);
    }, 3500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="chat-bubble-wrapper">
      <div className="bot-avatar">🤖</div>
      <div className={`chat-bubble ${visible ? 'chat--visible' : 'chat--hidden'}`}>
        <span className="bubble-text">{messages[currentIndex]}</span>
        {currentIndex === messages.length - 1 && (
          <div className="typing-dots">
            <span></span><span></span><span></span>
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatBubble;