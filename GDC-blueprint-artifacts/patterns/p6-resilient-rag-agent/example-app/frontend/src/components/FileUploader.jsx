import React, { useState } from 'react';
import { Upload, File, CheckCircle, AlertCircle, Loader2, Lock, Globe } from 'lucide-react';
import axios from 'axios';
import { useUser } from '../UserContext';

const FileUploader = ({ onUploadComplete }) => {
  const { user } = useUser();
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState(null); // 'success', 'error'
  const [message, setMessage] = useState('');
  const [scope, setScope] = useState('personal'); // 'personal' or 'shared'

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      uploadFile(files[0]);
    }
  };

  const handleFileSelect = (e) => {
    const files = e.target.files;
    if (files.length > 0) {
      uploadFile(files[0]);
    }
  };

  const uploadFile = async (file) => {
    setUploading(true);
    setStatus(null);
    setMessage('');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('scope', scope);

    try {
      const response = await axios.post('/api/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
          'X-User-ID': user.id,
          'X-User-Role': user.role
        },
      });
      
      setStatus('success');
      setMessage(`Uploaded ${file.name} to ${scope}`);
      if (onUploadComplete) onUploadComplete(file.name);
    } catch (error) {
      console.error('Upload error:', error);
      setStatus('error');
      setMessage(error.response?.data?.detail || `Failed to upload ${file.name}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="w-full space-y-3">
      {/* Scope Toggle */}
      <div className="flex bg-gray-900 p-1 rounded-lg">
        <button
          onClick={() => setScope('personal')}
          className={`flex-1 flex items-center justify-center gap-2 py-1.5 text-xs font-medium rounded-md transition-colors ${scope === 'personal' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-gray-200'
            }`}
        >
          <Lock className="w-3 h-3" /> Personal
        </button>
        <button
          onClick={() => setScope('shared')}
          disabled={user.role !== 'admin'}
          className={`flex-1 flex items-center justify-center gap-2 py-1.5 text-xs font-medium rounded-md transition-colors ${scope === 'shared'
              ? 'bg-blue-600 text-white'
              : user.role === 'admin'
                ? 'text-gray-400 hover:text-gray-200'
                : 'text-gray-600 cursor-not-allowed'
            }`}
          title={user.role !== 'admin' ? "Only Admins can upload to shared" : ""}
        >
          <Globe className="w-3 h-3" /> Shared
        </button>
      </div>

      <div
        className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer
          ${isDragging ? 'border-blue-500 bg-blue-50/10' : 'border-gray-600 hover:border-gray-500'}
          ${status === 'error' ? 'border-red-500/50 bg-red-500/10' : ''}
          ${status === 'success' ? 'border-green-500/50 bg-green-500/10' : ''}
        `}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => document.getElementById('fileInput').click()}
      >
        <input
          type="file"
          id="fileInput"
          className="hidden"
          onChange={handleFileSelect}
          disabled={uploading}
        />
        
        <div className="flex flex-col items-center justify-center space-y-2">
          {uploading ? (
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
          ) : status === 'success' ? (
            <CheckCircle className="w-8 h-8 text-green-500" />
          ) : status === 'error' ? (
            <AlertCircle className="w-8 h-8 text-red-500" />
          ) : (
            <Upload className="w-8 h-8 text-gray-400" />
          )}
          
          <div className="text-sm font-medium text-gray-400">
            {uploading ? 'Uploading...' : status === 'success' ? 'Upload Complete' : status === 'error' ? 'Upload Failed' : 'Click or Drag to Upload'}
          </div>
          
          {message && (
            <div className={`text-xs ${status === 'error' ? 'text-red-400' : 'text-green-400'}`}>
              {message}
            </div>
          )}
          
          {!uploading && !status && (
            <div className="text-xs text-gray-500">
              PDF, Images, Audio supported
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default FileUploader;
