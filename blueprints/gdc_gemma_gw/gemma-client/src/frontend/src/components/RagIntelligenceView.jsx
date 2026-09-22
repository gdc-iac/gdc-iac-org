import React, { useState } from 'react';
import { BookOpen, Search, FileText, CheckCircle2, Shield, Loader2, Sparkles } from 'lucide-react';
import api from '../api';

export default function RagIntelligenceView() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const suggestedQueries = [
    "What vulnerabilities were identified for supply convoys along Route 9 in Sector 9?",
    "Summarize lessons learned from Operation Vanguard Shield Phase 1 logistics and EW defense.",
    "What cyber reconnaissance indicators correlate with kinetic ground harassment in Sector 9?",
    "What is the recommended alternative resupply route for FOB Bravo?"
  ];

  const handleSearch = async (queryText) => {
    const q = queryText || query;
    if (!q.trim()) return;

    setLoading(true);
    try {
      const res = await api.post('/rag/query', { query: q, sector: 'Sector 9' });
      setResult(res.data);
    } catch (err) {
      alert("Intelligence query failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Top Banner */}
      <div className="p-6 border-b border-slate-800 bg-slate-900/60">
        <div className="flex items-center gap-2 mb-1">
          <BookOpen className="w-5 h-5 text-indigo-400" />
          <h2 className="text-lg font-bold tracking-tight text-white">All-Source Intelligence & Debriefs (P6 RAG)</h2>
        </div>
        <p className="text-xs text-slate-400">
          Synthesizes answers from unclassified operational cables, SITREPs, and after-action reports with grounded document citations.
        </p>

        {/* Search Input Box */}
        <div className="mt-4 flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Ask a question across Sector 9 tactical intelligence reports..."
              className="w-full pl-10 pr-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            />
          </div>
          <button
            onClick={() => handleSearch()}
            disabled={loading || !query.trim()}
            className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs flex items-center gap-2 shadow-md shadow-indigo-500/20 disabled:opacity-50 transition-all"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            <span>Synthesize</span>
          </button>
        </div>

        {/* Query Suggestions */}
        <div className="mt-3 flex flex-wrap gap-1.5 items-center">
          <span className="text-[11px] text-slate-500 mr-1">Suggested Inquiries:</span>
          {suggestedQueries.map((sq, i) => (
            <button
              key={i}
              onClick={() => {
                setQuery(sq);
                handleSearch(sq);
              }}
              className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:border-indigo-500/50 transition-colors"
            >
              {sq}
            </button>
          ))}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {loading && (
          <div className="text-center py-20">
            <Loader2 className="w-8 h-8 animate-spin mx-auto text-indigo-400 mb-3" />
            <p className="text-sm font-medium text-slate-300">Searching and cross-referencing all-source cables...</p>
            <p className="text-xs text-slate-500 mt-1">Generating grounded response via Gemma Inference Gateway</p>
          </div>
        )}

        {!loading && !result && (
          <div className="text-center py-16 text-slate-500 max-w-md mx-auto">
            <FileText className="w-12 h-12 mx-auto mb-3 text-slate-600 opacity-40" />
            <h3 className="text-sm font-semibold text-slate-300">Ready for All-Source Queries</h3>
            <p className="text-xs text-slate-400 mt-1">
              Select one of the suggested tactical questions above or type your own question to retrieve synthesized insights and citations.
            </p>
          </div>
        )}

        {!loading && result && (
          <div className="space-y-6 max-w-4xl mx-auto">
            {/* Answer Card */}
            <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900 shadow-xl">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
                <div className="flex items-center gap-2">
                  <Shield className="w-4 h-4 text-emerald-400" />
                  <span className="font-semibold text-xs tracking-wider uppercase text-slate-300">Tactical Intelligence Synthesis</span>
                </div>
                <div className="text-[11px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  Model: {result.model_used}
                </div>
              </div>

              <div className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">
                {result.answer}
              </div>
            </div>

            {/* Citations Grid */}
            {result.citations && result.citations.length > 0 && (
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-indigo-400" />
                  <span>Referenced All-Source Cables ({result.citations.length})</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {result.citations.map((cit, idx) => (
                    <div key={idx} className="p-3.5 rounded-xl border border-slate-800 bg-slate-900/70 hover:border-slate-700 transition-all">
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-mono text-xs text-indigo-400 font-semibold">{cit.report_id}</span>
                        <span className="text-[10px] text-slate-500 font-mono">{cit.source_agency}</span>
                      </div>
                      <div className="text-xs font-medium text-white mb-1">{cit.title}</div>
                      <p className="text-[11px] text-slate-400 leading-normal line-clamp-3">{cit.snippet}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
