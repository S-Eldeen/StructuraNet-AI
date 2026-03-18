import { ImageKitProvider as IKContext, upload } from '@imagekit/react';
import { useRef, useState } from 'react';
import './Upload.css';

const urlEndpoint = import.meta.env.VITE_IMAGE_KIT_ENDPOINT;
const publicKey = import.meta.env.VITE_IMAGE_KIT_PUBLIC_KEY;

const authenticator = async () => {
  const response = await fetch("http://localhost:3000/api/upload");
  if (!response.ok) throw new Error('Auth failed');
  return response.json();
};

const Upload = ({ onStart, onProgress, onSuccess }) => {
  const inputRef = useRef();
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    setProgress(0);
    if (onStart) onStart(file);

    try {
      const { signature, expire, token } = await authenticator();

      const response = await upload({
        file,
        fileName: file.name,
        signature,
        expire,
        token,
        publicKey,
        useUniqueFileName: true,
        onProgress: (event) => {
          const percent = Math.round((event.loaded / event.total) * 100);
          setProgress(percent);
          if (onProgress) onProgress(percent);
        },
      });

      if (onSuccess) onSuccess(response.filePath);
    } catch (error) {
      console.error('Upload error:', error);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="upload-wrapper">
      <input
        type="file"
        ref={inputRef}
        onChange={handleFileChange}
        accept="image/*"
        style={{ display: 'none' }}
      />
      <button
        type="button"
        className="upload-btn"
        onClick={() => inputRef.current.click()}
        disabled={isUploading}
      >
        {isUploading ? `${progress}%` : <img src="/attachment.png" alt="رفع" />}
      </button>
    </div>
  );
};

export default Upload;