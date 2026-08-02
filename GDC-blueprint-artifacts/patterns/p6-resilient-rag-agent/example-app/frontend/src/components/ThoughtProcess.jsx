import React, { useState } from 'react';
import { ChevronDown, ChevronRight, BrainCircuit } from 'lucide-react';

const ThoughtProcess = ({ thoughts }) => {
  const [isOpen, setIsOpen] = useState(false);

  if (!thoughts || thoughts.length === 0) return null;

  return (
    <div className="mt-2 mb-2 border border-gray-700 rounded-md bg-gray-800">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center w-full p-2 text-sm text-gray-300 hover:bg-gray-700 transition-colors rounded-t-md"
      >
        {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <BrainCircuit size={16} className="ml-2 mr-2 text-purple-400" />
        <span className="font-medium">Agent Thought Process</span>
      </button>
      
      {isOpen && (
        <div className="p-3 text-sm text-gray-300 space-y-2 border-t border-gray-700">
          {thoughts.map((thought, index) => (
            <div key={index} className="flex items-start">
              <span className="mr-2 text-gray-500">{index + 1}.</span>
              <div className="whitespace-pre-wrap">{thought}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ThoughtProcess;
