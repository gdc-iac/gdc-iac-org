import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, AlertCircle, Loader2, Square } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import api from '../api';

export default function ChatArea({ 
  messages, 
  setMessages, 
  selectedFiles, 
  selectedModel, 
  setSelectedModel, // Add setSelectedModel callback
  isThinkingEnabled,
  currentChatId, 
  setCurrentChatId,
  refreshChats 
}) {
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [onlyUseSources, setOnlyUseSources] = useState(false);
  const messagesEndRef = useRef(null);
  const abortControllerRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
      setMessages(prev => [...prev, { role: 'system', content: 'Stopped by user.' }]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    // Create new AbortController
    abortControllerRef.current = new AbortController();

    try {
      const res = await api.post('/chat', {
        message: userMsg.content,
        model: selectedModel,
        file_ids: selectedFiles,
        only_use_sources: onlyUseSources,
        chat_id: currentChatId,
        is_thinking_enabled: isThinkingEnabled
      }, {
        signal: abortControllerRef.current.signal
      });

      const modelMsg = { role: 'model', content: res.data.response };
      setMessages(prev => [...prev, modelMsg]);
      
      // Dynamically update the read-only badge header to display which model served this prompt
      if (res.data.model) {
        setSelectedModel(res.data.model);
      }
      
      if (!currentChatId) {
        setCurrentChatId(res.data.chat_id);
        refreshChats();
      }
    } catch (err) {
      if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') {
        console.log('Request canceled');
      } else {
        setMessages(prev => [...prev, {
          role: 'system',
          content: 'Error: ' + (err.response?.data?.detail || err.message)
        }]);
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-64px)] bg-white">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-gray-400">
            <Bot className="w-12 h-12 mb-4 opacity-20" />
            <p>Select files and start chatting with Gemini</p>
          </div>
        )}
        
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role !== 'user' && (
              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                {msg.role === 'system' ? <AlertCircle className="w-5 h-5 text-red-500" /> : <Bot className="w-5 h-5 text-blue-600" />}
              </div>
            )}
            
            <div className={`max-w-[80%] rounded-2xl px-5 py-3 ${
              msg.role === 'user' 
                ? 'bg-blue-600 text-white' 
                : msg.role === 'system'
                  ? 'bg-red-50 text-red-600 border border-red-100'
                  : 'bg-gray-100 text-gray-800'
            }`}>
              <ReactMarkdown className="prose prose-sm max-w-none dark:prose-invert">
                {msg.content}
              </ReactMarkdown>
            </div>

            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                <User className="w-5 h-5 text-gray-600" />
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="flex gap-4">
             <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
                <Bot className="w-5 h-5 text-blue-600" />
              </div>
              <div className="bg-gray-100 rounded-2xl px-5 py-3 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-gray-500" />
                <span className="text-sm text-gray-500">Thinking...</span>
              </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 border-t bg-white">
        <div className="max-w-4xl mx-auto">
          {selectedFiles.length > 0 && (
            <div className="mb-2 flex items-center gap-2 text-xs text-blue-600 bg-blue-50 w-fit px-2 py-1 rounded-full">
              <span className="font-medium">{selectedFiles.length} files attached</span>
            </div>
          )}
          
          <form onSubmit={handleSubmit} className="relative">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a question about your documents..."
              className="w-full pl-4 pr-12 py-3 rounded-xl border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none shadow-sm"
              disabled={isLoading}
            />
            {isLoading ? (
              <button
                type="button"
                onClick={handleStop}
                className="absolute right-2 top-2 p-1.5 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
                title="Stop generation"
              >
                <Square className="w-5 h-5 fill-current" />
              </button>
            ) : (
                <button
                  type="submit" 
                  disabled={!input.trim()}
                  className="absolute right-2 top-2 p-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <Send className="w-5 h-5" />
                </button>
            )}
          </form>
          
          <div className="mt-2 flex items-center gap-2">
            <label className="flex items-center gap-2 cursor-pointer text-xs text-gray-600 hover:text-gray-900 select-none">
              <input 
                type="checkbox" 
                checked={onlyUseSources} 
                onChange={(e) => setOnlyUseSources(e.target.checked)}
                className="rounded text-blue-600 focus:ring-blue-500" 
              />
              Strictly use provided sources
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}
