import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import AdminDashboard from './components/AdminDashboard';
import { UserProvider } from './UserContext';

function AppContent() {
  const [activeView, setActiveView] = useState('chat'); // 'chat' or 'admin'
  const [activeChatId, setActiveChatId] = useState(null);

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100 font-sans overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        activeView={activeView}
        setActiveView={setActiveView}
        activeChatId={activeChatId}
        setActiveChatId={setActiveChatId}
      />

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col relative">
        {activeView === 'chat' ? (
          <ChatInterface
            activeChatId={activeChatId}
            setActiveChatId={setActiveChatId}
          />
        ) : (
          <AdminDashboard />
        )}
      </main>
    </div>
  );
}

function App() {
  return (
    <UserProvider>
      <AppContent />
    </UserProvider>
  );
}

export default App;
