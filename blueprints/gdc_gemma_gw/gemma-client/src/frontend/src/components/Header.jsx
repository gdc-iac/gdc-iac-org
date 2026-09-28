import React, { useState, useEffect } from 'react';
import { User, Shield, LogOut } from 'lucide-react';

export default function Header({ currentUser, setCurrentUser, selectedModel, setSelectedModel, isThinkingEnabled, setIsThinkingEnabled, isIntelConsoleEnabled }) {
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
    <header className="h-16 border-b border-slate-800 bg-slate-900 flex items-center justify-between px-6 shadow-md text-slate-100">
      <div className="flex items-center gap-3">
        <div className="bg-blue-600 p-2 rounded-xl shadow-md shadow-blue-500/20">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="font-bold text-base text-white tracking-tight leading-tight">
            {isIntelConsoleEnabled ? "Joint Intelligence & Readiness Console" : "Gemma Client"}
          </h1>
          <p className="text-[10px] text-slate-400 font-mono">
            {isIntelConsoleEnabled ? "GDC-AG DECISION SUPPORT // JTF VANGUARD" : "MULTI-TENANT CHAT & REASONING"}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Active Model Engine Badge (Read-Only) */}
        <div className="flex items-center gap-2 bg-slate-800/90 text-slate-200 px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-700 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span className="font-mono">Engine: {models.find(m => m.id === selectedModel)?.name || models[0]?.name || 'Auto-Routing'}</span>
        </div>

        {/* Thinking Toggle */}
        <div className="flex items-center gap-2 border-l border-slate-800 pl-4 text-xs text-slate-300">
          <input
            type="checkbox"
            id="thinking-toggle"
            checked={isThinkingEnabled}
            onChange={(e) => setIsThinkingEnabled(e.target.checked)}
            className="w-3.5 h-3.5 accent-blue-600 rounded border-slate-700 bg-slate-800 cursor-pointer"
          />
          <label htmlFor="thinking-toggle" className="cursor-pointer select-none">
            🧠 Tactical CoT
          </label>
        </div>

        {/* User Switcher / Secure OIDC Identity Display */}
        <div className="flex items-center gap-2 border-l border-slate-800 pl-4">
          <User className="w-4 h-4 text-slate-400" />
          {import.meta.env.VITE_ENABLE_OIDC === 'true' ? (
            <div className="flex items-center gap-2.5">
              <span className="text-xs font-semibold text-slate-200">
                {currentUser.id} <span className="text-[9px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded border border-blue-500/30 font-bold uppercase tracking-wider">OIDC</span>
              </span>
              <button 
                onClick={() => {
                  sessionStorage.removeItem('oidc_access_token');
                  window.location.reload();
                }}
                className="text-[11px] bg-slate-800 hover:bg-red-500/20 text-slate-300 hover:text-red-400 px-2 py-1 rounded transition-colors font-medium border border-slate-700"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <select
              value={currentUser.id}
              onChange={handleUserChange}
              className="text-xs font-medium text-slate-200 bg-slate-800 border border-slate-700 rounded px-2 py-1 outline-none cursor-pointer"
            >
              {users.map(u => (
                <option key={u.id} value={u.id} className="bg-slate-900 text-slate-200">{u.name}</option>
              ))}
            </select>
          )}
        </div>
      </div>
    </header>
  );
}
