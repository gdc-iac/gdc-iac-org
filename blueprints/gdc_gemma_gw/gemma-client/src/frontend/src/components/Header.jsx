import React, { useState, useEffect } from 'react';
import { User, Shield, LogOut, ExternalLink } from 'lucide-react';

export default function Header({
  currentUser,
  setCurrentUser,
  selectedModel,
  setSelectedModel,
  activeModel,
  setActiveModel,
  isThinkingEnabled,
  setIsThinkingEnabled,
  isIntelConsoleEnabled,
  setIsIntelConsoleEnabled
}) {
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

  // Compute Port 8080 Gateway Admin URL automatically for Cloud Workstation or localhost
  const gatewayAdminUrl = (() => {
    const { protocol, hostname } = window.location;
    if (/^[0-9]+-w-/.test(hostname)) {
      return `${protocol}//${hostname.replace(/^[0-9]+-/, '8080-')}/`;
    }
    return `${protocol}//${hostname}:8080/`;
  })();

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

  const resolvedModelLabel = models.find(m => m.id === (activeModel || selectedModel))?.name || activeModel || selectedModel;

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-900 flex items-center justify-between px-6 shadow-md text-slate-100">
      <div className="flex items-center gap-3">
        <div className="bg-blue-600 p-2 rounded-xl shadow-md shadow-blue-500/20">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="font-bold text-base text-white tracking-tight leading-tight">
            {isIntelConsoleEnabled ? "Joint Intelligence & Readiness Console" : "Gemma Client (Dev & Multi-Tenant Chat)"}
          </h1>
          <p className="text-[10px] text-slate-400 font-mono">
            {isIntelConsoleEnabled ? "GDC-AG DECISION SUPPORT // JTF VANGUARD" : "MULTI-TENANT CHAT, FILE GROUNDING & REASONING"}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* UI Mode Switcher: E2E Intel Console <-> Standard Gemma Dev Client */}
        {typeof setIsIntelConsoleEnabled === 'function' && (
          <div className="flex items-center bg-slate-800 p-0.5 rounded-lg border border-slate-700 text-[11px] font-semibold">
            <button
              type="button"
              onClick={() => setIsIntelConsoleEnabled(true)}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                isIntelConsoleEnabled ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Switch to E2E Joint Intelligence & Readiness Console"
            >
              🛡️ Intel Console
            </button>
            <button
              type="button"
              onClick={() => setIsIntelConsoleEnabled(false)}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                !isIntelConsoleEnabled ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Switch to Standard Gemma Multi-Tenant Chat & Document Client"
            >
              💬 Gemma Client
            </button>
          </div>
        )}

        {/* Model Selector + Live Resolved Model Badge */}
        <div className="flex items-center gap-2 bg-slate-800/90 text-slate-200 px-2.5 py-1 rounded-lg text-xs font-semibold border border-slate-700 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" title={`Last Resolved Engine: ${resolvedModelLabel}`}></span>
          <select
            value={selectedModel}
            onChange={(e) => {
              setSelectedModel(e.target.value);
              if (typeof setActiveModel === 'function') {
                setActiveModel(e.target.value);
              }
            }}
            className="bg-transparent text-slate-100 font-mono text-xs outline-none cursor-pointer"
          >
            {models.map(m => (
              <option key={m.id} value={m.id} className="bg-slate-900 text-slate-100">
                {m.name}
              </option>
            ))}
          </select>
          {selectedModel === 'gemma4' && activeModel && activeModel !== 'gemma4' && (
            <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded border border-emerald-500/30 font-mono">
              → {activeModel}
            </span>
          )}
        </div>

        {/* Thinking Toggle */}
        <div className="flex items-center gap-2 border-l border-slate-800 pl-3 text-xs text-slate-300">
          <input
            type="checkbox"
            id="thinking-toggle"
            checked={isThinkingEnabled}
            onChange={(e) => setIsThinkingEnabled(e.target.checked)}
            className="w-3.5 h-3.5 accent-blue-600 rounded border-slate-700 bg-slate-800 cursor-pointer"
          />
          <label htmlFor="thinking-toggle" className="cursor-pointer select-none">
            🧠 CoT
          </label>
        </div>

        {/* Direct Link to Port 8080 Gateway Admin Control Plane */}
        <a
          href={gatewayAdminUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="hidden md:flex items-center gap-1 text-[11px] bg-slate-800 hover:bg-slate-700 text-blue-300 px-2.5 py-1 rounded-lg border border-slate-700 transition-colors font-medium"
          title="Open Gemma 4 Gateway Control Plane (Port 8080)"
        >
          ⚙️ Gateway Admin <ExternalLink className="w-3 h-3" />
        </a>

        {/* User Switcher / Secure OIDC Identity Display */}
        <div className="flex items-center gap-2 border-l border-slate-800 pl-3">
          <User className="w-4 h-4 text-slate-400" />
          {import.meta.env.VITE_ENABLE_OIDC === 'true' ? (
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-200">
                {currentUser.id} <span className="text-[9px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded border border-blue-500/30 font-bold uppercase tracking-wider">{currentUser.role || 'OIDC'}</span>
              </span>
              <button 
                onClick={() => {
                  const idToken = sessionStorage.getItem('oidc_id_token');
                  sessionStorage.removeItem('oidc_access_token');
                  sessionStorage.removeItem('oidc_refresh_token');
                  sessionStorage.removeItem('oidc_id_token');
                  const authority = import.meta.env.VITE_OIDC_AUTHORITY || `${window.location.origin}/auth/realms/gdc-rag-realm`;
                  const clientId = import.meta.env.VITE_OIDC_CLIENT_ID || 'rag-frontend';
                  const redirectUri = encodeURIComponent(window.location.origin);
                  const hintParam = idToken ? `&id_token_hint=${encodeURIComponent(idToken)}` : '';
                  window.location.href = `${authority}/protocol/openid-connect/logout?client_id=${clientId}&post_logout_redirect_uri=${redirectUri}${hintParam}`;
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
