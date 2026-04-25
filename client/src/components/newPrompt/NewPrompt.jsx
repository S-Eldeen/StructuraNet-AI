import { useState } from 'react';
import { useAuth } from '@clerk/clerk-react';
import Upload from '../upload/Upload';
import { askGeminiStream } from '../../lib/gemini';
import './newPrompt.css';

const NewPrompt = ({ addMessage, setIsTyping, chatId, history = [] }) => {
  const [text, setText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [images, setImages] = useState([]);
  const [isListening, setIsListening] = useState(false);
  const { getToken } = useAuth();

  const handleUploadStart = (file) => {
    const previewUrl = URL.createObjectURL(file);
    setImages((prev) => [...prev, { file, filePath: null, progress: 0, previewUrl }]);
  };

  const handleUploadProgress = (percent) => {
    setImages((prev) => {
      const lastIndex = prev.length - 1;
      if (lastIndex < 0) return prev;

      const last = prev[lastIndex];
      if (last.filePath) return prev;

      const updated = [...prev];
      updated[lastIndex] = { ...last, progress: percent };
      return updated;
    });
  };

  const handleUploadSuccess = (filePath) => {
    setImages((prev) => {
      const lastIndex = prev.length - 1;
      if (lastIndex < 0) return prev;

      const updated = [...prev];
      updated[lastIndex] = { ...updated[lastIndex], filePath, progress: 100 };
      return updated;
    });
  };

  const removeImage = (index) => {
    setImages((prev) => prev.filter((_, i) => i !== index));
  };

  const startListening = () => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert('المتصفح لا يدعم التعرف على الصوت. يرجى استخدام Chrome أو Edge.');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'ar-EG';
    recognition.continuous = false;
    recognition.interimResults = false;

    setIsListening(true);

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setText((prev) => prev + (prev ? ' ' : '') + transcript);
      setIsListening(false);
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
      alert('حدث خطأ أثناء التعرف على الصوت. حاول مرة أخرى.');
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.start();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isLoading) return;

    const completedImages = images
      .filter((img) => img.filePath)
      .map((img) => img.filePath);

    const hasText = text.trim() !== '';
    const hasImages = completedImages.length > 0;

    if (!hasText && !hasImages) return;

    const userMessage = {
      role: 'user',
      content: text,
      images: completedImages,
    };

    addMessage(userMessage);

    setText('');
    setImages([]);
    setIsLoading(true);
    setIsTyping(true);

    const aiMessageId = Date.now() + Math.random();

    addMessage({
      role: 'assistant',
      content: '',
      id: aiMessageId,
      streaming: true,
    });

    try {
      let accumulatedText = '';

      const conversation = [
        ...history
          .filter((msg) => msg.content && !msg.streaming)
          .map((msg) => ({
            role: msg.role === 'user' ? 'user' : 'assistant',
            content: msg.content,
          })),
        {
          role: 'user',
          content: text,
        },
      ];

      await askGeminiStream(conversation, completedImages, (partialText) => {
        accumulatedText = partialText;

        addMessage(
          {
            role: 'assistant',
            content: accumulatedText,
            id: aiMessageId,
            streaming: true,
          },
          true
        );
      });

      addMessage(
        {
          role: 'assistant',
          content: accumulatedText,
          id: aiMessageId,
          streaming: false,
        },
        true
      );

      if (chatId) {
        const token = await getToken({ skipCache: true });

        await fetch(`http://localhost:3000/api/chats/${chatId}/messages`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            messages: [
              userMessage,
              { role: 'assistant', content: accumulatedText },
            ],
          }),
        });
      }
    } catch (error) {
      console.error('AI Error:', error);

      addMessage(
        {
          role: 'assistant',
          content: 'عذراً، حدث خطأ. حاول مرة أخرى.',
          id: aiMessageId,
          streaming: false,
        },
        true
      );
    } finally {
      setIsLoading(false);
      setIsTyping(false);
    }
  };

  return (
    <div className="newPrompt">
      <form onSubmit={handleSubmit}>
        {images.length > 0 && (
          <div className="previews-row">
            {images.map((img, idx) => (
              <div key={idx} className="preview-item large">
                <img src={img.previewUrl} alt="preview" />

                {!img.filePath && (
                  <div className="progress-overlay">
                    <span>{Math.round(img.progress)}%</span>
                  </div>
                )}

                {img.filePath && (
                  <button
                    type="button"
                    className="remove-preview"
                    onClick={() => removeImage(idx)}
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="input-row">
          <Upload
            onStart={handleUploadStart}
            onProgress={handleUploadProgress}
            onSuccess={handleUploadSuccess}
          />

          <input
            type="text"
            className="text-input"
            placeholder={isLoading ? 'Thinking...' : 'Ask Structranet AI'}
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={isLoading}
          />

          <button
            type="button"
            className={`mic-btn ${isListening ? 'listening' : ''}`}
            onClick={startListening}
            disabled={isLoading}
            title="إدخال صوتي"
          >
            <img src="/microphone.png" alt="mic" className="mic-icon" />
          </button>

          <button
            type="submit"
            className="send-btn"
            disabled={
              isLoading ||
              (!text.trim() && images.filter((img) => img.filePath).length === 0)
            }
          >
            <img src="/arrow.png" alt="send" />
          </button>
        </div>
      </form>
    </div>
  );
};

export default NewPrompt;