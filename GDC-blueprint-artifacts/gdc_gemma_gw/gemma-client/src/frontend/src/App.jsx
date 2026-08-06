import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import api from './api';
import { decodeJwt, exchangeCodeForTokens, redirectToLogin } from './oidc';
import { Loader2 } from 'lucide-react';

function App() {
  const isOidcEnabled = import.meta.env.VITE_ENABLE_OIDC === 'true';
  const authority = import.meta.env.VITE_OIDC_AUTHORITY || (window.location.origin + '/auth/realms/gdc-rag-realm');
  const clientId = import.meta.env.VITE_OIDC_CLIENT_ID || 'rag-frontend';

  // State
  const [currentUser, setCurrentUser] = useState({ 
    id: sessionStorage.getItem('userId') || 'user1', 
    role: sessionStorage.getItem('userRole') || 'user' 
  });
  const [oidcAuthenticated, setOidcAuthenticated] = useState(false);
  const [oidcLoading, setOidcLoading] = useState(isOidcEnabled);

  const [selectedModel, setSelectedModel] = useState('gemma4');
  const [activeModel, setActiveModel] = useState('gemma4'); // New UI display state!
  const [isThinkingEnabled, setIsThinkingEnabled] = useState(true);
  
  const [files, setFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  
  const [chats, setChats] = useState([]);
  const [currentChatId, setCurrentChatId] = useState(null);
  const [messages, setMessages] = useState([]);

  // OIDC Handshake Hook
  useEffect(() => {
    if (!isOidcEnabled) return;

    const handleAuth = async () => {
      const urlParams = new URLSearchParams(window.location.search);
      const code = urlParams.get('code');
      const state = urlParams.get('state');
      const storedToken = sessionStorage.getItem('oidc_access_token');
      
      if (storedToken) {
        const decoded = decodeJwt(storedToken);
        if (decoded && decoded.exp * 1000 > Date.now()) {
          const username = decoded.preferred_username || decoded.sub;
          const isAdmin = decoded.realm_access?.roles?.includes('admin');
          
          setCurrentUser({
            id: username,
            role: isAdmin ? 'admin' : 'user',
            token: storedToken
          });
          setOidcAuthenticated(true);
          setOidcLoading(false);
          return;
        } else {
          sessionStorage.removeItem('oidc_access_token');
        }
      }

      if (code && state) {
        try {
          const tokenData = await exchangeCodeForTokens(authority, clientId, code, state);
          const accessToken = tokenData.access_token;
          sessionStorage.setItem('oidc_access_token', accessToken);
          
          // Wipe authorization code query strings from browser URL preview bar
          window.history.replaceState({}, document.title, window.location.pathname);
          
          const decoded = decodeJwt(accessToken);
          const username = decoded.preferred_username || decoded.sub;
          const isAdmin = decoded.realm_access?.roles?.includes('admin');
          
          setCurrentUser({
            id: username,
            role: isAdmin ? 'admin' : 'user',
            token: accessToken
          });
          setOidcAuthenticated(true);
        } catch (err) {
          console.error("Token exchange failed", err);
          alert("Keycloak session handover failed: " + err.message);
        } finally {
          setOidcLoading(false);
        }
      } else {
        try {
          await redirectToLogin(authority, clientId);
        } catch (err) {
          console.error("Login redirect aborted", err);
          setOidcLoading(false);
        }
      }
    };

    handleAuth();
  }, []);

  // Initial Load (Gated behind dynamic verification handshakes)
  useEffect(() => {
    if (isOidcEnabled && !oidcAuthenticated) return;
    fetchFiles();
    fetchChats();
  }, [currentUser.id, oidcAuthenticated]);

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

  if (isOidcEnabled && oidcLoading) {
    return (
      <div className="flex h-screen bg-gray-900 items-center justify-center text-white font-sans">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 animate-spin text-blue-500" />
          <h2 className="text-lg font-semibold">Contacting Secure Identity Gateway...</h2>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-white text-gray-900 font-sans">
      <Header 
        currentUser={currentUser} 
        setCurrentUser={setCurrentUser}
        selectedModel={activeModel} // Render activeModel on the badge
        setSelectedModel={setActiveModel} // Update activeModel on switcher click
        isThinkingEnabled={isThinkingEnabled}
        setIsThinkingEnabled={setIsThinkingEnabled}
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
          selectedModel={selectedModel} // Always send generic gemma4 to API
          setSelectedModel={setActiveModel} // Update activeModel badge on API response
          isThinkingEnabled={isThinkingEnabled}
          currentChatId={currentChatId}
          setCurrentChatId={setCurrentChatId}
          refreshChats={fetchChats}
        />
      </div>
    </div>
  );
}

export default App;
