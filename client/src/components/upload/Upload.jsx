import { upload } from '@imagekit/react';
import { useRef, useState, useEffect } from 'react';
import './Upload.css';

const urlEndpoint = import.meta.env.VITE_IMAGE_KIT_ENDPOINT;
const publicKey = import.meta.env.VITE_IMAGE_KIT_PUBLIC_KEY;

const authenticator = async () => {
  const response = await fetch("http://localhost:3000/api/upload");
  if (!response.ok) throw new Error('Auth failed');
  return response.json();
};

const Upload = ({ onStart, onProgress, onSuccess }) => {
  const imageRef = useRef();
  const fileRef = useRef();
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef();

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleFileUpload = async (file) => {
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
    <div className="upload-wrapper" ref={dropdownRef}>
      {/* Hidden inputs */}
      <input
        type="file"
        ref={imageRef}
        onChange={(e) => { handleFileUpload(e.target.files[0]); setShowDropdown(false); }}
        accept="image/*"
        style={{ display: 'none' }}
      />
      <input
        type="file"
        ref={fileRef}
        onChange={(e) => { handleFileUpload(e.target.files[0]); setShowDropdown(false); }}
        accept=".pdf,.doc,.docx,.txt,.csv,.json,.xml,.zip"
        style={{ display: 'none' }}
      />

      {/* Main button */}
      <button
        type="button"
        className="upload-btn"
        onClick={() => !isUploading && setShowDropdown((prev) => !prev)}
        disabled={isUploading}
      >
        {isUploading ? `${progress}%` : <img src="/attachment.png" alt="رفع" />}
      </button>

      {/* Dropdown */}
      {showDropdown && !isUploading && (
        <div className="upload-dropdown">
          <button
            type="button"
            className="upload-option"
            onClick={() => { imageRef.current.click(); setShowDropdown(false); }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M16 5h6"/><path d="M19 2v6"/>
              <path d="M21 11.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7.5"/>
              <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
              <circle cx="9" cy="9" r="2"/>
            </svg>
            <span>Add Image</span>
          </button>
          <button
            type="button"
            className="upload-option"
            onClick={() => { fileRef.current.click(); setShowDropdown(false); }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M11.35 22H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.706.706l3.588 3.588A2.4 2.4 0 0 1 20 8v5.35"/>
              <path d="M14 2v5a1 1 0 0 0 1 1h5"/>
              <path d="M14 19h6"/><path d="M17 16v6"/>
            </svg>
            <span>Add File</span>
          </button>
        </div>
      )}
    </div>
  );
};

export default Upload;
