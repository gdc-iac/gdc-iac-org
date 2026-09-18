/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
