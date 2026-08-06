import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_URL,
});

// Add a request interceptor to inject the User ID
api.interceptors.request.use((config) => {
  const userId = localStorage.getItem('userId') || 'user1';
  const userRole = localStorage.getItem('userRole') || 'user';
  
  config.headers['X-User-ID'] = userId;
  config.headers['X-User-Role'] = userRole;
  return config;
});

export default api;
