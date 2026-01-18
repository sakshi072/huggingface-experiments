import React from 'react';
import type { ChatMessage } from '../../types/chat-types';

interface MessageProps {
  message: ChatMessage;
}

export const Message: React.FC<MessageProps> = ({ message }) => {
  const isUser = message.role === 'user';
  const className = isUser 
    ? 'bg-blue-500 text-white self-end' 
    : 'bg-gray-100 text-gray-800 self-start';
    
  let statusIndicator = null;
  if (message.status === 'loading' && !isUser) {
    statusIndicator = <span className="text-xs text-gray-500 ml-2">...</span>;
  } else if (message.status === 'error' && !isUser) {
    statusIndicator = <span className="text-xs text-red-500 ml-2">⚠️ Error</span>;
  }

  return (
    <div className={`max-w-4xl p-3 my-2 rounded-xl shadow ${className}`}>
      <p className="font-semibold capitalize">{isUser ? 'You' : 'HUGG'}</p>
      <div className="whitespace-pre-wrap">
        {message.content}
        {statusIndicator}
      </div>
    </div>
  );
};