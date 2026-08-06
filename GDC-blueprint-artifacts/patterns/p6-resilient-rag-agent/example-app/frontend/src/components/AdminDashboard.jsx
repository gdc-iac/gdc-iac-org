import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Trash2, RefreshCw, Database, AlertCircle, Lock, User, Globe } from 'lucide-react';
import { useUser } from '../UserContext';

const AdminDashboard = () => {
  const { user } = useUser();
  const [documents, setDocuments] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const headers = {
        'X-User-ID': user.id,
        'X-User-Role': user.role
      };

      // Fetch documents (filtered by backend based on user)
      const docsRes = await axios.get('/api/documents', { headers });
      setDocuments(docsRes.data);

      // Only fetch stats if admin (optional, or we can make stats endpoint public/filtered too)
      // For now, let's try to fetch stats, but handle 403 gracefully if we restricted it.
      try {
        const statsRes = await axios.get('/api/admin/stats', { headers });
        setStats(statsRes.data);
      } catch (e) {
        // Ignore stats error for non-admins
        setStats(null);
      }

    } catch (err) {
      setError('Failed to fetch documents. Ensure backend is running.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [user]);

  const handleDelete = async (filename) => {
    if (!window.confirm(`Are you sure you want to delete "${filename}"? This will remove it from the database and GCS.`)) {
      return;
    }

    try {
      await axios.delete(`/api/documents/${filename}`, {
        headers: {
          'X-User-ID': user.id,
          'X-User-Role': user.role
        }
      });
      // Refresh list
      fetchData();
    } catch (err) {
      alert('Failed to delete document: ' + (err.response?.data?.detail || err.message));
    }
  };

  if (loading && !documents.length) {
    return <div className="p-8 text-center text-gray-400">Loading Knowledge Base...</div>;
  }

  return (
    <div className="h-full flex flex-col bg-gray-900 text-white p-6 overflow-y-auto">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Database className="w-6 h-6 text-blue-400" />
          {user.role === 'admin' ? 'Knowledge Base (Admin)' : 'My Documents'}
        </h1>
        <button 
          onClick={fetchData} 
          className="p-2 bg-gray-800 hover:bg-gray-700 rounded-full transition-colors"
          title="Refresh Data"
        >
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      {error && (
        <div className="bg-red-900/50 border border-red-500 text-red-200 p-4 rounded-lg mb-6 flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          {error}
        </div>
      )}

      {/* Stats Panel (Admin Only) */}
      {stats && user.role === 'admin' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
            <div className="text-gray-400 text-sm">Total Documents</div>
            <div className="text-3xl font-bold text-white">{stats.total_documents}</div>
          </div>
          <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
            <div className="text-gray-400 text-sm">Valid Embeddings (768d)</div>
            <div className="text-3xl font-bold text-green-400">{stats.valid_embeddings}</div>
          </div>
          <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
            <div className="text-gray-400 text-sm">Invalid/Null Embeddings</div>
            <div className="text-3xl font-bold text-red-400">
              {stats.total_documents - stats.valid_embeddings}
            </div>
          </div>
        </div>
      )}

      {/* Documents Table */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-gray-700/50 text-gray-300 text-sm uppercase tracking-wider">
              <th className="p-4 font-medium">ID</th>
              <th className="p-4 font-medium">Filename</th>
              <th className="p-4 font-medium">Scope</th>
              <th className="p-4 font-medium">Content Preview</th>
              <th className="p-4 font-medium">Dims</th>
              <th className="p-4 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {documents.length === 0 ? (
              <tr>
                <td colSpan="6" className="p-8 text-center text-gray-500">
                  No documents found.
                </td>
              </tr>
            ) : (
              documents.map((doc) => (
                <tr key={doc.id} className="hover:bg-gray-700/30 transition-colors">
                  <td className="p-4 text-gray-400 font-mono text-sm">#{doc.id}</td>
                  <td className="p-4 font-medium text-blue-300">{doc.filename}</td>
                  <td className="p-4">
                    {doc.owner_id ? (
                      <span className="flex items-center gap-1 text-xs font-medium text-purple-400 bg-purple-900/30 px-2 py-1 rounded border border-purple-800">
                        <User size={12} /> Personal
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs font-medium text-blue-400 bg-blue-900/30 px-2 py-1 rounded border border-blue-800">
                        <Globe size={12} /> Shared
                      </span>
                    )}
                  </td>
                  <td className="p-4 text-gray-400 text-sm truncate max-w-xs">
                    {doc.preview}...
                  </td>
                  <td className="p-4">
                    <span className={`px-2 py-1 rounded text-xs font-mono ${doc.embedding_dims === 768 ? 'bg-green-900/50 text-green-300 border border-green-700' : 'bg-red-900/50 text-red-300 border border-red-700'}`}>
                      {doc.embedding_dims}
                    </span>
                  </td>
                  <td className="p-4 text-right">
                    <button
                      onClick={() => handleDelete(doc.filename)}
                      className="p-2 text-red-400 hover:text-red-300 hover:bg-red-900/20 rounded transition-colors"
                      title="Delete Document"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default AdminDashboard;
