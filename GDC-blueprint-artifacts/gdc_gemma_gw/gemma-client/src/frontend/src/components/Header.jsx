import React, { useState, useEffect } from 'react';
import { User, Shield, LogOut } from 'lucide-react';

export default function Header({ currentUser, setCurrentUser, selectedModel, setSelectedModel, isThinkingEnabled, setIsThinkingEnabled }) {
  const users = [
    { id: 'user1', name: 'Alice (User)', role: 'user' },
    { id: 'user2', name: 'Bob (User)', role: 'user' },
    { id: 'admin', name: 'Charlie (Admin)', role: 'admin' },
  ];

  const [models, setModels] = useState([
    { id: 'gemma4', name: 'Gemma 4 Gateway (Auto)' },
    { id: 'gemma4:26b', name: 'Gemma 4 26B A4B (MoE)' },
    { id: 'gemma4:31b', name: 'Gemma 4 31B (Dense)' }
  ]);

  useEffect(() => {
    fetch('/api/models')
      .then(res => res.json())
      .then(data => {
        if (data && data.length > 0) {
          const prependedData = [
            { id: 'gemma4', name: 'Gemma 4 Gateway (Auto)' },
            ...data
          ];
          setModels(prependedData);
          // Exclude default 'gemma4' auto selection from resetting
          const found = prependedData.find(m => m.id === selectedModel);
          if (!found && selectedModel !== 'gemma4') {
            setSelectedModel(prependedData[0].id);
          }
        }
      })
      .catch(err => console.error("Error fetching serving models:", err));
  }, []);

  const handleUserChange = (e) => {
    const user = users.find(u => u.id === e.target.value);
    setCurrentUser(user);
    sessionStorage.setItem('userId', user.id);
    sessionStorage.setItem('userRole', user.role);
    window.location.reload();
  };

  return (
    <header className="h-16 border-b bg-white flex items-center justify-between px-6 shadow-sm">
      <div className="flex items-center gap-2">
        <div className="bg-blue-600 p-2 rounded-lg">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <h1 className="font-bold text-xl text-gray-800">Gemma Client</h1>
      </div>

      <div className="flex items-center gap-4">
        {/* Active Model Engine Badge (Read-Only) */}
        <div className="flex items-center gap-2 bg-slate-50 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          <span>Model: {models.find(m => m.id === selectedModel)?.name || models[0]?.name || 'Loading active model...'}</span>
        </div>

        {/* Thinking Toggle */}
        <div className="flex items-center gap-2 border-l pl-4 text-sm text-gray-600">
          <input
            type="checkbox"
            id="thinking-toggle"
            checked={isThinkingEnabled}
            onChange={(e) => setIsThinkingEnabled(e.target.checked)}
            className="w-4 h-4 accent-blue-600 rounded border-gray-300 outline-none"
          />
          <label htmlFor="thinking-toggle" className="cursor-pointer font-medium select-none">
            🧠 Thinking Process
          </label>
        </div>

        {/* User Switcher / Secure OIDC Identity Display */}
        <div className="flex items-center gap-2 border-l pl-4">
          <User className="w-4 h-4 text-gray-500" />
          {import.meta.env.VITE_ENABLE_OIDC === 'true' ? (
            <div className="flex items-center gap-3">
              <span className="text-sm font-semibold text-gray-700">
                {currentUser.id} <span className="text-[10px] bg-blue-50 text-blue-600 px-1 rounded border border-blue-200 font-bold">Secure (OIDC)</span>
              </span>
              <button 
                onClick={() => {
                  sessionStorage.removeItem('oidc_access_token');
                  window.location.reload();
                }}
                className="text-xs bg-slate-100 hover:bg-red-50 text-slate-600 hover:text-red-600 px-2 py-1 rounded transition-colors font-medium border"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <select
              value={currentUser.id}
              onChange={handleUserChange}
              className="text-sm font-medium text-gray-700 bg-transparent outline-none cursor-pointer"
            >
              {users.map(u => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </select>
          )}
        </div>
      </div>
    </header>
  );
}
