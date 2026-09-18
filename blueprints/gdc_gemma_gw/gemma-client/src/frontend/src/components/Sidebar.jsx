import React, { useState, useEffect } from 'react';
import { Plus, Trash2, FileText, Image as ImageIcon, Upload, Loader2, MessageSquare, Eye } from 'lucide-react';
import api from '../api';

export default function Sidebar({ 
  currentUser, 
  files, 
  setFiles, 
  selectedFiles, 
  setSelectedFiles,
  chats,
  setChats,
  currentChatId,
  setCurrentChatId,
  loadChat
}) {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadScope, setUploadScope] = useState('personal'); // personal | shared

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('is_shared', uploadScope === 'shared');

    try {
      const res = await api.post('/upload', formData);
      // Refresh files list
      const newFile = {
        ...res.data,
        uploaded_at: new Date().toISOString(),
        file_size_bytes: file.size,
        content_type: file.type,
        is_shared: uploadScope === 'shared',
        user_id: currentUser.id
      };
      setFiles([newFile, ...files]);
    } catch (err) {
      alert('Upload failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteFile = async (fileId, e) => {
    e.stopPropagation();
    if (!confirm('Delete this file?')) return;
    try {
      await api.delete(`/files/${fileId}`);
      setFiles(files.filter(f => f.id !== fileId));
      setSelectedFiles(selectedFiles.filter(id => id !== fileId));
    } catch (err) {
      alert('Delete failed');
    }
  };

  const handleViewFile = (fileId, e) => {
    e.stopPropagation();
    // Use window.open to view in new tab
    // We need to construct the URL. Since we use proxy, it's /api/files/{id}/content
    // But we need to handle auth if we were using tokens. Here we rely on browser session or headers?
    // Wait, window.open won't send custom headers (X-User-ID).
    // This is a limitation of the current simple Auth.
    // However, for Stepping Stone, we can pass user_id as query param or just rely on the fact that 
    // we are not strictly enforcing auth for this demo view if we don't check headers in the GET endpoint?
    // Actually, I added `user: User = Depends(get_current_user)` to the endpoint.
    // `get_current_user` checks headers. Browser navigation won't send headers.

    // Workaround for Demo: Pass user_id in query param and update auth.py to check it?
    // Or just fetch blob in JS and create object URL?
    // Fetching blob is better for headers.

    fetchFileBlob(fileId);
  };

  const fetchFileBlob = async (fileId) => {
    try {
      const res = await api.get(`/files/${fileId}/content`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: res.headers['content-type'] }));
      window.open(url, '_blank');
    } catch (err) {
      alert('Failed to view file');
    }
  };

  const toggleFileSelection = (fileId) => {
    if (selectedFiles.includes(fileId)) {
      setSelectedFiles(selectedFiles.filter(id => id !== fileId));
    } else {
      setSelectedFiles([...selectedFiles, fileId]);
    }
  };

  const handleDeleteChat = async (chatId, e) => {
    e.stopPropagation();
    if (!confirm('Delete this chat?')) return;
    try {
      await api.delete(`/chats/${chatId}`);
      setChats(chats.filter(c => c.id !== chatId));
      if (currentChatId === chatId) setCurrentChatId(null);
    } catch (err) {
      alert('Delete failed');
    }
  };

  return (
    <div className="w-80 bg-gray-50 border-r flex flex-col h-[calc(100vh-64px)]">
      {/* New Chat Button */}
      <div className="p-4 border-b">
        <button 
          onClick={() => setCurrentChatId(null)}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Chat
        </button>
      </div>

      {/* Files Section */}
      <div className="flex-1 overflow-y-auto p-4 border-b min-h-[40%]">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Context Files</h3>
        
        {/* Upload Area */}
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-2">
            <select 
              value={uploadScope}
              onChange={(e) => setUploadScope(e.target.value)}
              className="text-xs border rounded px-1 py-0.5 bg-white"
              disabled={currentUser.role !== 'admin'}
            >
              <option value="personal">Personal</option>
              {currentUser.role === 'admin' && <option value="shared">Shared</option>}
            </select>
            <label className="flex-1 cursor-pointer bg-white border border-dashed border-gray-300 rounded-md p-2 flex items-center justify-center gap-2 hover:bg-gray-50 transition-colors">
              <input type="file" className="hidden" onChange={handleFileUpload} disabled={isUploading} />
              {isUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4 text-gray-500" />}
              <span className="text-xs text-gray-600">Upload File</span>
            </label>
          </div>
        </div>

        {/* File List */}
        <div className="space-y-2">
          {files.length === 0 && <p className="text-xs text-gray-400 text-center py-4">No files uploaded</p>}
          {files.map(file => (
            <div 
              key={file.id}
              onClick={() => toggleFileSelection(file.id)}
              className={`group flex items-center justify-between p-2 rounded-md cursor-pointer border transition-all ${
                selectedFiles.includes(file.id) 
                  ? 'bg-blue-50 border-blue-200 ring-1 ring-blue-200' 
                  : 'bg-white border-gray-200 hover:border-blue-200'
              }`}
            >
              <div className="flex items-center gap-2 overflow-hidden">
                {file.content_type?.startsWith('image/') ? (
                  <ImageIcon className="w-4 h-4 text-purple-500 flex-shrink-0" />
                ) : (
                  <FileText className="w-4 h-4 text-blue-500 flex-shrink-0" />
                )}
                <div className="flex flex-col overflow-hidden">
                  <span className="text-sm text-gray-700 truncate">{file.filename}</span>
                  <span className="text-[10px] text-gray-400 flex items-center gap-1">
                    {file.is_shared ? <span className="text-green-600 bg-green-50 px-1 rounded">Shared</span> : 'Personal'}
                    <span>•</span>
                    {(file.file_size_bytes / 1024).toFixed(1)} KB
                  </span>
                </div>
              </div>
              <div className="flex items-center opacity-0 group-hover:opacity-100 transition-all">
                <button
                  onClick={(e) => handleViewFile(file.id, e)}
                  className="p-1 hover:bg-blue-50 rounded text-gray-400 hover:text-blue-500"
                  title="View"
                >
                  <Eye className="w-3 h-3" />
                </button>
                {(file.user_id === currentUser.id || currentUser.role === 'admin') && (
                  <button
                    onClick={(e) => handleDeleteFile(file.id, e)}
                    className="p-1 hover:bg-red-50 rounded text-gray-400 hover:text-red-500"
                    title="Delete"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Chat History Section */}
      <div className="flex-1 overflow-y-auto p-4 bg-gray-50">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">History</h3>
        <div className="space-y-1">
          {chats.map(chat => (
            <div 
              key={chat.id}
              onClick={() => loadChat(chat.id)}
              className={`group flex items-center justify-between p-2 rounded-md cursor-pointer text-sm ${
                currentChatId === chat.id ? 'bg-white shadow-sm text-blue-600' : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <div className="flex items-center gap-2 overflow-hidden">
                <MessageSquare className="w-4 h-4 flex-shrink-0" />
                <span className="truncate">{chat.title || 'New Chat'}</span>
              </div>
              <button 
                onClick={(e) => handleDeleteChat(chat.id, e)}
                className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-50 rounded text-gray-400 hover:text-red-500"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
