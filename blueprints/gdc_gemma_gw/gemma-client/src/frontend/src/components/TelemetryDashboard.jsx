import React, { useState, useEffect } from 'react';
import { Activity, Radio, ShieldAlert, Satellite, Globe, Cpu, RefreshCw, Zap, Filter } from 'lucide-react';
import api from '../api';

export default function TelemetryDashboard() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedDomain, setSelectedDomain] = useState('ALL');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [expandedEventId, setExpandedEventId] = useState(null);

  const fetchEvents = async () => {
    try {
      setLoading(true);
      const url = selectedDomain === 'ALL' ? '/telemetry/events' : `/telemetry/events?domain=${selectedDomain}`;
      const res = await api.get(url);
      setEvents(res.data || []);
    } catch (err) {
      console.error("Failed to fetch telemetry events:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvents();
  }, [selectedDomain]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(() => {
      fetchEvents();
    }, 4000);
    return () => clearInterval(timer);
  }, [autoRefresh, selectedDomain]);

  const handleSimulate = async () => {
    try {
      setSimulating(true);
      await api.post('/telemetry/simulate?count=5');
      await fetchEvents();
    } catch (err) {
      alert("Simulation error: " + (err.response?.data?.detail || err.message));
    } finally {
      setSimulating(false);
    }
  };

  const domainIcons = {
    LAND: ShieldAlert,
    AIR: Radio,
    SEA: Globe,
    SPACE: Satellite,
    CYBER: Cpu
  };

  const threatColors = {
    CRITICAL: 'bg-red-500/20 text-red-400 border-red-500/40',
    HIGH: 'bg-orange-500/20 text-orange-400 border-orange-500/40',
    MEDIUM: 'bg-amber-500/20 text-amber-400 border-amber-500/40',
    LOW: 'bg-blue-500/20 text-blue-400 border-blue-500/40'
  };

  const domainCounts = events.reduce((acc, ev) => {
    acc[ev.domain] = (acc[ev.domain] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Top Banner / Domain Metrics */}
      <div className="p-6 border-b border-slate-800 bg-slate-900/60">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-5">
          <div>
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-blue-400 animate-pulse" />
              <h2 className="text-lg font-bold tracking-tight text-white">Multi-Domain Sensor Telemetry (Kafka Ingestion)</h2>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Live buffered tactical feeds from Land, Air, Sea, Space, and Cyber sensors across Sector 9.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                autoRefresh
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                  : 'bg-slate-800 border-slate-700 text-slate-400'
              }`}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${autoRefresh ? 'animate-spin' : ''}`} />
              <span>{autoRefresh ? 'Live Stream: Active' : 'Polling: Paused'}</span>
            </button>

            <button
              onClick={handleSimulate}
              disabled={simulating}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white shadow-md shadow-blue-500/20 disabled:opacity-50 transition-all"
            >
              <Zap className="w-3.5 h-3.5" />
              <span>{simulating ? 'Ingesting...' : '⚡ Ingest Sensor Pings'}</span>
            </button>
          </div>
        </div>

        {/* Domain Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {['LAND', 'AIR', 'SEA', 'SPACE', 'CYBER'].map((dom) => {
            const Icon = domainIcons[dom] || Activity;
            const count = domainCounts[dom] || 0;
            const isSelected = selectedDomain === dom;
            return (
              <div
                key={dom}
                onClick={() => setSelectedDomain(isSelected ? 'ALL' : dom)}
                className={`cursor-pointer p-3 rounded-xl border transition-all ${
                  isSelected
                    ? 'bg-blue-600/20 border-blue-500 shadow-sm shadow-blue-500/20'
                    : 'bg-slate-900 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                  <span className="font-semibold uppercase tracking-wider text-[11px]">{dom}</span>
                  <Icon className={`w-4 h-4 ${isSelected ? 'text-blue-400' : 'text-slate-500'}`} />
                </div>
                <div className="text-xl font-bold text-white">{count}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">Active Signals</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="px-6 py-2.5 bg-slate-900/40 border-b border-slate-800 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <span className="text-slate-400 mr-2">Domain Filter:</span>
          {['ALL', 'LAND', 'AIR', 'SEA', 'SPACE', 'CYBER'].map((d) => (
            <button
              key={d}
              onClick={() => setSelectedDomain(d)}
              className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${
                selectedDomain === d
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              {d}
            </button>
          ))}
        </div>
        <div className="text-[11px] text-slate-400">
          Showing <span className="text-white font-mono">{events.length}</span> events
        </div>
      </div>

      {/* Event Stream List */}
      <div className="flex-1 overflow-y-auto p-6 space-y-3">
        {events.length === 0 ? (
          <div className="text-center py-16 text-slate-500">
            <Activity className="w-10 h-10 mx-auto mb-2 text-slate-600 opacity-50" />
            <p className="text-sm">No sensor telemetry events detected in buffer.</p>
            <p className="text-xs text-slate-600 mt-1">Click "⚡ Ingest Sensor Pings" above to generate live signals.</p>
          </div>
        ) : (
          events.map((ev) => {
            const Icon = domainIcons[ev.domain] || Activity;
            const isExpanded = expandedEventId === ev.id;
            return (
              <div
                key={ev.id || `${ev.sensor_id}-${ev.event_timestamp}`}
                className="p-3.5 rounded-xl border border-slate-800 bg-slate-900 hover:border-slate-700 transition-all cursor-pointer"
                onClick={() => setExpandedEventId(isExpanded ? null : ev.id)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-blue-400 mt-0.5">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm text-white">{ev.title}</span>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold ${threatColors[ev.threat_level] || threatColors.LOW}`}>
                          {ev.threat_level}
                        </span>
                        <span className="text-xs font-mono text-slate-500">{ev.sensor_id}</span>
                      </div>
                      <p className="text-xs text-slate-300 mt-1">{ev.summary}</p>
                      
                      <div className="flex items-center gap-4 text-[11px] text-slate-500 mt-2 font-mono">
                        <span>Sector: {ev.sector}</span>
                        {ev.latitude && ev.longitude && (
                          <span>Coords: {ev.latitude.toFixed(4)}, {ev.longitude.toFixed(4)}</span>
                        )}
                        <span>{new Date(ev.event_timestamp).toLocaleTimeString()}</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-xs text-slate-500 hover:text-slate-300">
                    {isExpanded ? 'Collapse ▲' : 'Payload ▼'}
                  </div>
                </div>

                {isExpanded && ev.raw_payload && (
                  <div className="mt-3 pt-3 border-t border-slate-800/80">
                    <div className="text-[10px] uppercase font-bold tracking-wider text-slate-400 mb-1">Raw Telemetry Payload:</div>
                    <pre className="p-2.5 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-emerald-400 overflow-x-auto">
                      {JSON.stringify(ev.raw_payload, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
