import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_URL,
});

// Add a request interceptor to inject the User ID
api.interceptors.request.use((config) => {
  const oidcToken = sessionStorage.getItem('oidc_access_token');
  
  if (oidcToken) {
    // Inject secure dynamic OIDC bearer token
    config.headers['Authorization'] = `Bearer ${oidcToken}`;
  } else {
    // Standard mock user simulation headers (Baseline / Local Tests)
    const userId = sessionStorage.getItem('userId') || 'user1';
    const userRole = sessionStorage.getItem('userRole') || 'user';
    config.headers['X-User-ID'] = userId;
    config.headers['X-User-Role'] = userRole;
  }
  return config;
});

export default api;
