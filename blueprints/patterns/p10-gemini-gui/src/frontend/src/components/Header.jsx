import React from 'react';
import { User, Shield, LogOut } from 'lucide-react';

export default function Header({ currentUser, setCurrentUser, selectedModel, setSelectedModel }) {
  const users = [
    { id: 'user1', name: 'Alice (User)', role: 'user' },
    { id: 'user2', name: 'Bob (User)', role: 'user' },
    { id: 'admin', name: 'Charlie (Admin)', role: 'admin' },
  ];

  const models = [
    { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
    { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
    { id: 'gemini-3.0-flash-preview', name: 'Gemini 3.0 Flash (Preview)' },
    { id: 'gemini-3.0-pro-preview', name: 'Gemini 3.0 Pro (Preview)' },
  ];

  const handleUserChange = (e) => {
    const user = users.find(u => u.id === e.target.value);
    setCurrentUser(user);
    localStorage.setItem('userId', user.id);
    localStorage.setItem('userRole', user.role);
    window.location.reload(); // Simple reload to refresh data
  };

  return (
    <header className="h-16 border-b bg-white flex items-center justify-between px-6 shadow-sm">
      <div className="flex items-center gap-2">
        <div className="bg-blue-600 p-2 rounded-lg">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <h1 className="font-bold text-xl text-gray-800">Gemini GUI</h1>
      </div>

      <div className="flex items-center gap-4">
        {/* Model Selector */}
        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          className="border rounded-md px-3 py-1.5 text-sm bg-gray-50 focus:ring-2 focus:ring-blue-500 outline-none"
        >
          {models.map(m => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </select>

        {/* User Switcher */}
        <div className="flex items-center gap-2 border-l pl-4">
          <User className="w-4 h-4 text-gray-500" />
          <select
            value={currentUser.id}
            onChange={handleUserChange}
            className="text-sm font-medium text-gray-700 bg-transparent outline-none cursor-pointer"
          >
            {users.map(u => (
              <option key={u.id} value={u.id}>{u.name}</option>
            ))}
          </select>
        </div>
      </div>
    </header>
  );
}
