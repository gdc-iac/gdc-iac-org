import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import api from './api';

function App() {
  // State
  const [currentUser, setCurrentUser] = useState({ 
    id: localStorage.getItem('userId') || 'user1', 
    role: localStorage.getItem('userRole') || 'user' 
  });
  const [selectedModel, setSelectedModel] = useState('gemini-2.5-flash');
  
  const [files, setFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  
  const [chats, setChats] = useState([]);
  const [currentChatId, setCurrentChatId] = useState(null);
  const [messages, setMessages] = useState([]);

  // Initial Load
  useEffect(() => {
    fetchFiles();
    fetchChats();
  }, [currentUser.id]);

  // Load Chat Messages
  useEffect(() => {
    if (currentChatId) {
      fetchMessages(currentChatId);
    } else {
      setMessages([]);
    }
  }, [currentChatId]);

  const fetchFiles = async () => {
    try {
      const res = await api.get('/files');
      setFiles(res.data);
    } catch (err) {
      console.error("Failed to fetch files", err);
    }
  };

  const fetchChats = async () => {
    try {
      const res = await api.get('/chats');
      setChats(res.data);
    } catch (err) {
      console.error("Failed to fetch chats", err);
    }
  };

  const fetchMessages = async (chatId) => {
    try {
      const res = await api.get(`/chats/${chatId}/messages`);
      setMessages(res.data);
    } catch (err) {
      console.error("Failed to fetch messages", err);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-white text-gray-900 font-sans">
      <Header 
        currentUser={currentUser} 
        setCurrentUser={setCurrentUser}
        selectedModel={selectedModel}
        setSelectedModel={setSelectedModel}
      />
      
      <div className="flex flex-1 overflow-hidden">
        <Sidebar 
          currentUser={currentUser}
          files={files}
          setFiles={setFiles}
          selectedFiles={selectedFiles}
          setSelectedFiles={setSelectedFiles}
          chats={chats}
          setChats={setChats}
          currentChatId={currentChatId}
          setCurrentChatId={setCurrentChatId}
          loadChat={setCurrentChatId}
        />
        
        <ChatArea 
          messages={messages}
          setMessages={setMessages}
          selectedFiles={selectedFiles}
          selectedModel={selectedModel}
          currentChatId={currentChatId}
          setCurrentChatId={setCurrentChatId}
          refreshChats={fetchChats}
        />
      </div>
    </div>
  );
}

export default App;
