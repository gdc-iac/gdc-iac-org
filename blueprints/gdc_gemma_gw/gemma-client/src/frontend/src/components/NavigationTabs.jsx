import React from 'react';
import { Activity, BookOpen, Database, MessageSquare } from 'lucide-react';

export default function NavigationTabs({ activeTab, setActiveTab }) {
  const tabs = [
    { id: 'telemetry', label: 'Tactical Feeds (Kafka)', icon: Activity, badge: 'Live Stream' },
    { id: 'rag', label: 'All-Source Intel (RAG)', icon: BookOpen, badge: 'SITREPs' },
    { id: 'audit', label: 'Operational Readiness (SQL)', icon: Database, badge: 'Agentic' },
    { id: 'chat', label: 'Tactical Chat', icon: MessageSquare, badge: 'Gemma 4' },
  ];

  return (
    <div className="bg-slate-900 border-b border-slate-800 px-6 py-2 flex items-center justify-between">
      <div className="flex items-center space-x-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                isActive
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                  isActive
                    ? 'bg-blue-800 text-blue-200'
                    : 'bg-slate-800 text-slate-400 border border-slate-700'
                }`}
              >
                {tab.badge}
              </span>
            </button>
          );
        })}
      </div>
      <div className="text-[11px] text-slate-400 flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
        <span className="font-mono text-slate-300">OP VANGUARD SHIELD // SECTOR 9</span>
      </div>
    </div>
  );
}
