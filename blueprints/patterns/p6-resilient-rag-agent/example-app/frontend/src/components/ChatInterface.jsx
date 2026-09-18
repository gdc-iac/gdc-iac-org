import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Loader2 } from 'lucide-react';
import axios from 'axios';
import ThoughtProcess from './ThoughtProcess';
import { useUser } from '../UserContext';

const ChatInterface = ({ activeChatId, setActiveChatId }) => {
  const { user } = useUser();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load chat history when activeChatId changes
  useEffect(() => {
    const loadChatHistory = async () => {
      if (!activeChatId) {
        setMessages([
          { role: 'assistant', content: 'Hello! I am your Agentic Data Analyst. Upload a document or ask me a question to get started.' }
        ]);
        return;
      }

      setIsLoading(true);
      try {
        const response = await axios.get(`/api/chats/${activeChatId}`, {
          headers: {
            'X-User-ID': user.id,
            'X-User-Role': user.role
          }
        });
        // Transform history to match message format
        const history = response.data.map(msg => ({
          role: msg.role,
          content: msg.content,
          // Note: History might not have thoughts/context persisted in simple schema, 
          // but if we wanted to persist them, we'd need to update the DB schema further.
          // For now, we just show content.
        }));
        setMessages(history);
      } catch (error) {
        console.error("Failed to load chat history:", error);
        setMessages([{ role: 'assistant', content: 'Failed to load chat history.' }]);
      } finally {
        setIsLoading(false);
      }
    };

    loadChatHistory();
  }, [activeChatId, user]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await axios.post('/api/query', {
        query: userMessage.content,
        chat_id: activeChatId
      }, {
        headers: {
          'X-User-ID': user.id,
          'X-User-Role': user.role
        }
      });
      
      const assistantMessage = {
        role: 'assistant',
        content: response.data.answer,
        thoughts: response.data.thoughts || [], 
        context: response.data.context_used,
        source_document: response.data.source_document
      };
      
      setMessages(prev => [...prev, assistantMessage]);

      // If this was a new chat, update the activeChatId
      if (!activeChatId && response.data.chat_id) {
        setActiveChatId(response.data.chat_id);
      }

    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'Sorry, I encountered an error processing your request.',
        isError: true
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-900 rounded-lg shadow-sm border border-gray-800 overflow-hidden">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`flex max-w-[80%] ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
              
              {/* Avatar */}
              <div className={`flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center mx-2 
                ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-purple-600 text-white'}`}>
                {msg.role === 'user' ? <User size={18} /> : <Bot size={18} />}
              </div>

              {/* Message Bubble */}
              <div className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                <div className={`p-3 rounded-lg text-sm shadow-sm
                  ${msg.role === 'user' 
                    ? 'bg-blue-600 text-white rounded-tr-none'
                    : 'bg-gray-800 border border-gray-700 text-gray-100 rounded-tl-none'}`}>
                  {msg.content}
                </div>
                
                {/* Thoughts (Assistant only) */}
                {msg.role === 'assistant' && msg.thoughts && msg.thoughts.length > 0 && (
                  <div className="w-full max-w-md">
                    <ThoughtProcess thoughts={msg.thoughts} />
                  </div>
                )}
                
                {/* Context/Citations (Assistant only) */}
                {msg.role === 'assistant' && (msg.source_document || msg.context) && (
                  <div className="mt-1 text-xs text-gray-500 max-w-md truncate flex items-center gap-1">
                    <span className="font-semibold">Source:</span>
                    {msg.source_document ? msg.source_document : `${msg.context.substring(0, 50)}...`}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
             <div className="flex flex-row items-center mx-2">
                <div className="flex-shrink-0 h-8 w-8 rounded-full bg-purple-600 text-white flex items-center justify-center mr-2">
                  <Bot size={18} />
                </div>
              <div className="bg-gray-800 border border-gray-700 p-3 rounded-lg rounded-tl-none">
                <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
                </div>
             </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 border-t border-gray-800 bg-gray-900">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about your documents..."
            className="flex-1 p-2 bg-gray-800 border border-gray-700 text-white rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent placeholder-gray-500"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="p-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send size={20} />
          </button>
        </form>
      </div>
    </div>
  );
};

export default ChatInterface;
