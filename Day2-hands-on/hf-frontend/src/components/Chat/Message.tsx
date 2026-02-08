import React from 'react';
import type { ChatMessage } from '../../types/chat-types';

interface MessageProps {
  message: ChatMessage;
}

export const Message: React.FC<MessageProps> = ({ message }) => {
  const isUser = message.role === 'user';
  const isThinking = message.status === 'Thinking';
  const isLoading = message.status === 'Loading';
  const isError = message.status === 'error';

  const bubbleClasses = isUser 
    ? 'bg-blue-600 text-white self-end rounded-br-none' 
    : isThinking 
      ? 'bg-blue-50 text-blue-700 self-start rounded-bl-none border border-blue-100'
      : 'bg-gray-100 text-gray-800 self-start rounded-bl-none';
    
  let statusIndicator = null;
  if (message.status === 'loading' && !isUser) {
    statusIndicator = <span className="text-xs text-gray-500 ml-2">...</span>;
  } else if (message.status === 'error' && !isUser) {
    statusIndicator = <span className="text-xs text-red-500 ml-2">⚠️ Error</span>;
  }

  return (
    <div className={`max-w-[85%] p-4 my-2 rounded-2xl shadow-sm transition-all duration-200 ${bubbleClasses}`}>
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs font-bold uppercase tracking-wider opacity-70">
          {isUser ? 'You' : 'HUGG AI'}
        </p>
        
        {/* Animated Status Indicator */}
        {!isUser && (isThinking || isLoading) && (
          <div className="flex space-x-1">
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce"></span>
          </div>
        )}
      </div>

      <div className={`whitespace-pre-wrap text-sm leading-relaxed ${isThinking ? 'italic opacity-90' : ''}`}>
        {/* If thinking, we might want to prefix with a search icon */}
        {isThinking && <span className="mr-2">🔍</span>}
        
        {message.content}
        
        {isError && (
          <span className="block mt-2 text-xs text-red-500 font-medium">
            ⚠️ System Error: Unable to complete request
          </span>
        )}
      </div>
    </div>
  );
};