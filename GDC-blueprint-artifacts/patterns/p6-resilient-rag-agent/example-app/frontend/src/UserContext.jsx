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
