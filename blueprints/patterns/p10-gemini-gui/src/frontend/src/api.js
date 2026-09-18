/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
