import React, { useState } from 'react';
import { Database, Search, ShieldCheck, Terminal, AlertTriangle, Loader2, Sparkles, Clock, FileSpreadsheet } from 'lucide-react';
import api from '../api';

export default function ReadinessAuditView() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const suggestedQueries = [
    "List all military units in Sector 9 and their combat readiness ratings.",
    "List all military units in Sector 9 with combat readiness below C2.",
    "Check fuel reserves, days of supply, and resupply status at all forward operating bases.",
    "Show equipment inventory, operational counts, and readiness percentage for TF-3-ARMOR.",
    "List all convoy supply routes, their current status, and chokepoint assessments."
  ];

  const handleQuery = async (queryText) => {
    const q = queryText || query;
    if (!q.trim()) return;

    setLoading(true);
    try {
      const res = await api.post('/analyst/query', { query: q });
      setResult(res.data);
    } catch (err) {
      alert("Database query audit failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const getReadinessBadge = (val) => {
    if (val === 'C1') return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">C1 (Ready)</span>;
    if (val === 'C2') return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">C2 (Minor Deficiencies)</span>;
    if (val === 'C3') return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-orange-500/20 text-orange-400 border border-orange-500/30">C3 (Marginal)</span>;
    if (val === 'C4') return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">C4 (Not Ready)</span>;
    if (val === 'OPEN') return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">OPEN</span>;
    if (val === 'AMBER') return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">AMBER</span>;
    if (val === 'CLOSED') return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">CLOSED</span>;
    return val;
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Top Banner */}
      <div className="p-6 border-b border-slate-800 bg-slate-900/60">
        <div className="flex items-center gap-2 mb-1">
          <Database className="w-5 h-5 text-emerald-400" />
          <h2 className="text-lg font-bold tracking-tight text-white">Agentic Data Analyst (P7 SQL Audit)</h2>
        </div>
        <p className="text-xs text-slate-400">
          Enables commanders to independently audit operational readiness and force assets in plain English with strict read-only safeguards.
        </p>

        {/* Input Box */}
        <div className="mt-4 flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
              placeholder="Ask an operational readiness question in plain English..."
              className="w-full pl-10 pr-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all"
            />
          </div>
          <button
            onClick={() => handleQuery()}
            disabled={loading || !query.trim()}
            className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center gap-2 shadow-md shadow-emerald-500/20 disabled:opacity-50 transition-all"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            <span>Audit</span>
          </button>
        </div>

        {/* Suggested Queries */}
        <div className="mt-3 flex flex-wrap gap-1.5 items-center">
          <span className="text-[11px] text-slate-500 mr-1">Command Questions:</span>
          {suggestedQueries.map((sq, i) => (
            <button
              key={i}
              onClick={() => {
                setQuery(sq);
                handleQuery(sq);
              }}
              className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:border-emerald-500/50 transition-colors"
            >
              {sq}
            </button>
          ))}
        </div>
      </div>

      {/* Main Results View */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {loading && (
          <div className="text-center py-20">
            <Loader2 className="w-8 h-8 animate-spin mx-auto text-emerald-400 mb-3" />
            <p className="text-sm font-medium text-slate-300">Translating commander query into safe read-only SQL...</p>
            <p className="text-xs text-slate-500 mt-1">Executing query against operational database and generating insight</p>
          </div>
        )}

        {!loading && !result && (
          <div className="text-center py-16 text-slate-500 max-w-md mx-auto">
            <FileSpreadsheet className="w-12 h-12 mx-auto mb-3 text-slate-600 opacity-40" />
            <h3 className="text-sm font-semibold text-slate-300">Operational Database Ready</h3>
            <p className="text-xs text-slate-400 mt-1">
              Ask a question above to generate verifiable read-only SQL queries and view asset readiness tables.
            </p>
          </div>
        )}

        {!loading && result && (
          <div className="space-y-6 max-w-5xl mx-auto">
            {/* Executive Summary Card */}
            <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900 shadow-xl">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-emerald-400" />
                  <span className="font-semibold text-xs tracking-wider uppercase text-slate-300">Commander Executive Summary</span>
                </div>
                <div className="text-[11px] font-mono text-slate-500">
                  Model: {result.model_used}
                </div>
              </div>
              <p className="text-sm text-slate-200 leading-relaxed font-medium">
                {result.summary}
              </p>
            </div>

            {/* Generated SQL Audit Card */}
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/70">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-blue-400" />
                  <span className="font-mono text-xs font-semibold text-slate-300">Generated Safe SQL Query</span>
                </div>
                <div className="flex items-center gap-3 text-[11px] text-slate-400">
                  <span className="flex items-center gap-1 text-emerald-400 font-mono">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    Read-Only Guard Verified
                  </span>
                  <span className="flex items-center gap-1 font-mono text-slate-300">
                    <Clock className="w-3 h-3 text-emerald-400" />
                    DB Engine: {result.execution_time_ms} ms
                  </span>
                  {result.total_latency_seconds && (
                    <span className="text-[10px] text-slate-500 font-mono">
                      (Total AI Pipeline: {result.total_latency_seconds}s)
                    </span>
                  )}
                </div>
              </div>
              <pre className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono text-emerald-400 overflow-x-auto">
                {result.generated_sql}
              </pre>
            </div>

            {/* Structured Results Table */}
            <div>
              <div className="flex items-center justify-between mb-3 text-xs text-slate-400">
                <div className="font-semibold uppercase tracking-wider text-slate-300">
                  Database Records ({result.row_count} rows retrieved)
                </div>
              </div>

              {result.results && result.results.length > 0 ? (
                <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900">
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-800/80 border-b border-slate-700 text-slate-300 uppercase text-[10px] tracking-wider font-semibold">
                        <tr>
                          {Object.keys(result.results[0]).map((key) => (
                            <th key={key} className="px-4 py-3 font-semibold">
                              {key.replace(/_/g, ' ')}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800 font-mono">
                        {result.results.map((row, rIdx) => (
                          <tr key={rIdx} className="hover:bg-slate-800/50 transition-colors">
                            {Object.entries(row).map(([k, v], cIdx) => (
                              <td key={cIdx} className="px-4 py-3 text-slate-300">
                                {getReadinessBadge(String(v ?? ''))}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="p-6 rounded-xl border border-slate-800 bg-slate-900 text-center text-slate-500 text-xs">
                  Query executed successfully, but returned 0 rows matching criteria.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
