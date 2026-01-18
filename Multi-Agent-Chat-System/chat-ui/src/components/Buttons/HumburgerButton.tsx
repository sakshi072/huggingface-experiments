import React from 'react';

interface HamburgerButtonProps {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
}

export const HamburgerButton: React.FC<HamburgerButtonProps> = ({ isOpen, setIsOpen }) => {
  return (
    <button
      onClick={() => setIsOpen(!isOpen)}
      className="p-2 text-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-400 transition-all duration-300 ease-in-out"
      aria-label="Toggle Menu"
    >
      <div className="flex flex-col justify-center items-center h-5 w-5">
        
        {/* Top bar - Static */}
        <span
          className={`block w-5 h-0.5 bg-gray-700 transition-all duration-300 ease-in-out -translate-y-1`}
        ></span>
        
        {/* Middle bar - Static */}
        <span
          className={`block w-5 h-0.5 bg-gray-700 transition-all duration-300 ease-in-out opacity-100`}
        ></span>
        
        {/* Bottom bar - Static */}
        <span
          className={`block w-5 h-0.5 bg-gray-700 transition-all duration-300 ease-in-out translate-y-1`}
        ></span>
      </div>
    </button>
  );
};