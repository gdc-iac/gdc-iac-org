import axios from 'axios';
import { refreshAccessToken } from './oidc';

const API_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_URL,
});

// Add a request interceptor to inject the User ID & silently refresh nearing-expiry tokens
api.interceptors.request.use(async (config) => {
  let oidcToken = sessionStorage.getItem('oidc_access_token');
  
  if (oidcToken) {
    try {
      const parts = oidcToken.split('.');
      if (parts.length === 3) {
        const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
        // If token expires in less than 45 seconds, silently refresh it
        if (payload.exp && payload.exp * 1000 < Date.now() + 45000) {
          const authority = import.meta.env.VITE_OIDC_AUTHORITY || (window.location.origin + '/auth/realms/gdc-rag-realm');
          const clientId = import.meta.env.VITE_OIDC_CLIENT_ID || 'rag-frontend';
          const freshToken = await refreshAccessToken(authority, clientId);
          if (freshToken) oidcToken = freshToken;
        }
      }
    } catch (e) {
      // Ignore parse errors, proceed with existing token
    }

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

// Automatically handle expired tokens and retry failed requests seamlessly
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response && error.response.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const authority = import.meta.env.VITE_OIDC_AUTHORITY || (window.location.origin + '/auth/realms/gdc-rag-realm');
      const clientId = import.meta.env.VITE_OIDC_CLIENT_ID || 'rag-frontend';
      const freshToken = await refreshAccessToken(authority, clientId);
      if (freshToken) {
        originalRequest.headers['Authorization'] = `Bearer ${freshToken}`;
        return api(originalRequest);
      }
      // If refresh fails, clear tokens and reload
      sessionStorage.removeItem('oidc_access_token');
      sessionStorage.removeItem('oidc_refresh_token');
      if (import.meta.env.VITE_ENABLE_OIDC === 'true') {
        window.location.reload();
      }
    }
    return Promise.reject(error);
  }
);

export default api;
