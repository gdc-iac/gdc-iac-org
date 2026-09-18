import React, { useState, useEffect } from 'react';
import { MessageSquare, Settings, Database, Shield, User, Trash2, History } from 'lucide-react';
import FileUploader from './FileUploader';
import { useUser } from '../UserContext';

const Sidebar = ({ activeView, setActiveView, activeChatId, setActiveChatId }) => {
  const { user, login, personas } = useUser();
  const [chats, setChats] = useState([]);

  // Fetch chats when user changes
  useEffect(() => {
    const fetchChats = async () => {
      try {
        const response = await fetch('/api/chats', {
          headers: {
            'X-User-ID': user.id,
            'X-User-Role': user.role
          }
        });
        if (response.ok) {
          const data = await response.json();
          setChats(data);
        }
      } catch (error) {
        console.error("Failed to fetch chats:", error);
      }
    };
    fetchChats();
    // Reset active chat when user changes
    setActiveChatId(null);
  }, [user, setActiveChatId]);

  const deleteChat = async (chatId, e) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this chat?")) return;
    try {
      const response = await fetch(`/api/chats/${chatId}`, {
        method: 'DELETE',
        headers: {
          'X-User-ID': user.id,
          'X-User-Role': user.role
        }
      });
      if (response.ok) {
        setChats(chats.filter(c => c.id !== chatId));
        if (activeChatId === chatId) setActiveChatId(null);
      }
    } catch (error) {
      console.error("Failed to delete chat:", error);
    }
  };

  return (
    <div className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col h-full">
      {/* Header & User Switcher */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-6 h-6 text-blue-500" />
          <h1 className="font-bold text-lg tracking-tight">Resilient RAG v2</h1>
        </div>

        <div className="relative">
          <select
            value={user.id}
            onChange={(e) => login(e.target.value)}
            className="w-full bg-gray-900 border border-gray-600 text-gray-300 text-sm rounded-md p-2 focus:ring-blue-500 focus:border-blue-500 block"
          >
            {personas.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Navigation */}
      <div className="p-4 space-y-2">
        <button
          onClick={() => { setActiveView('chat'); setActiveChatId(null); }}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
            activeView === 'chat' && activeChatId === null
              ? 'bg-blue-600 text-white' 
              : 'text-gray-400 hover:bg-gray-700 hover:text-white'
          }`}
        >
          <MessageSquare className="w-5 h-5" />
          <span className="font-medium">New Chat</span>
        </button>

        <button
          onClick={() => setActiveView('admin')}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${activeView === 'admin'
            ? 'bg-blue-600 text-white'
            : 'text-gray-400 hover:bg-gray-700 hover:text-white'
            }`}
        >
          <Database className="w-5 h-5" />
          <span className="font-medium">Knowledge Base</span>
        </button>
      </div>

      {/* Chat History */}
      <div className="flex-1 overflow-y-auto px-4 py-2">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-2">
          <History className="w-3 h-3" /> Recent Chats
        </h2>
        <div className="space-y-1">
          {chats.map(chat => (
            <div
              key={chat.id}
              onClick={() => { setActiveView('chat'); setActiveChatId(chat.id); }}
              className={`group flex items-center justify-between text-sm p-2 rounded cursor-pointer transition-colors ${activeChatId === chat.id ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-700/50'
                }`}
            >
              <span className="truncate w-40">{chat.title || "New Chat"}</span>
              <button
                onClick={(e) => deleteChat(chat.id, e)}
                className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
          {chats.length === 0 && (
            <div className="text-xs text-gray-600 italic">No history yet</div>
          )}
        </div>
      </div>

      {/* Upload Zone */}
      <div className="p-4 border-t border-gray-700">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Ingestion</h2>
        <FileUploader />
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-700">
        <div className="flex items-center justify-between p-2 bg-gray-900/50 rounded text-sm">
          <span className="text-gray-400">Mode</span>
          <span className="text-xs text-green-400 font-medium flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-green-500"></span>
            Online
          </span>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
