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

import React, { createContext, useState, useContext, useEffect } from 'react';

const UserContext = createContext();

export const useUser = () => useContext(UserContext);

export const UserProvider = ({ children }) => {
  // Default to a simple user
  const [user, setUser] = useState({
    id: 'user1',
    role: 'user',
    name: 'Alice (User)'
  });

  const personas = [
    { id: 'user1', role: 'user', name: 'Alice (User)' },
    { id: 'user2', role: 'user', name: 'Bob (User)' },
    { id: 'admin', role: 'admin', name: 'Charlie (Admin)' }
  ];

  const login = (personaId) => {
    const persona = personas.find(p => p.id === personaId);
    if (persona) {
      setUser(persona);
    }
  };

  return (
    <UserContext.Provider value={{ user, login, personas }}>
      {children}
    </UserContext.Provider>
  );
};
