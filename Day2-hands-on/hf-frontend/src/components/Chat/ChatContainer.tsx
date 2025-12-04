import React, { useEffect, useRef, useCallback } from 'react';
import type { ChatMessage } from '../../types/chat-types';
import { Message } from './Message';
import { PromptInput } from './PromptInput';

interface ChatContainerProps {
  messages: ChatMessage[];
  isLoading: boolean;
  isPaginating?: boolean;
  hasMore?: boolean;
  loadPreviousMessages?: () => void;
  sendMessage: (prompt: string) => Promise<void>;
}

export const ChatContainer: React.FC<ChatContainerProps> = ({
  messages,
  isLoading,
  isPaginating = false,
  hasMore = false,
  loadPreviousMessages,
  sendMessage
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const previousScrollHeightRef = useRef<number>(0);
  const isLoadingMoreRef = useRef<boolean>(false);

  // Auto-scroll to bottom on new messages (but not when loading history)
  useEffect(() => {
    if (!isPaginating && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length, isPaginating]);

  // Save scroll height before loading more messages
  useEffect(() => {
    if (isPaginating && containerRef.current) {
      previousScrollHeightRef.current = containerRef.current.scrollHeight;
    }
  }, [isPaginating]);

  // Restore scroll position after loading more messages
  useEffect(() => {
    if (!isPaginating && previousScrollHeightRef.current > 0 && containerRef.current) {
      const newScrollHeight = containerRef.current.scrollHeight;
      const heightDifference = newScrollHeight - previousScrollHeightRef.current;
      containerRef.current.scrollTop = heightDifference;
      previousScrollHeightRef.current = 0;
    }
  }, [isPaginating, messages]);

  // Handle scroll for infinite loading
  const handleScroll = useCallback(() => {
    if (!containerRef.current || !loadPreviousMessages) return;
    if (isPaginating || !hasMore || isLoadingMoreRef.current) return;

    const { scrollTop } = containerRef.current;

    // Load more when scrolled near the top (within 200px)
    if (scrollTop < 200) {
      isLoadingMoreRef.current = true;
      loadPreviousMessages();
      
      setTimeout(() => {
        isLoadingMoreRef.current = false;
      }, 1000);
    }
  }, [loadPreviousMessages, isPaginating, hasMore]);

  // Handle keyboard scroll events
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!containerRef.current || !loadPreviousMessages) return;
    if (isPaginating || !hasMore || isLoadingMoreRef.current) return;

    const { scrollTop } = containerRef.current;

    // Check for up arrow, page up, or home key near top of scroll
    if ((e.key === 'ArrowUp' || e.key === 'PageUp' || e.key === 'Home') && scrollTop < 200) {
      isLoadingMoreRef.current = true;
      loadPreviousMessages();
      
      setTimeout(() => {
        isLoadingMoreRef.current = false;
      }, 1000);
    }
  }, [loadPreviousMessages, isPaginating, hasMore]);

  // Attach scroll and keyboard listeners
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    container.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('keydown', handleKeyDown);
    
    return () => {
      container.removeEventListener('scroll', handleScroll);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleScroll, handleKeyDown]);

  return (
    <div className="flex flex-col h-full">
      <div 
        ref={containerRef}
        className="flex-grow overflow-y-auto p-4 mb-20 scrollbar-hide"
        style={{
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
        }}
      >
        <div className="flex flex-col max-w-4xl mx-auto">
          {/* Loading indicator at top */}
          {isPaginating && (
            <div className="text-center py-4 text-blue-600 bg-blue-50 rounded mb-2">
              <span className="text-sm">Loading more messages...</span>
            </div>
          )}

          {/* No more messages indicator */}
          {!hasMore && messages.length > 0 && (
            <div className="text-center py-4 text-gray-400">
              <span className="text-sm">• Beginning of conversation •</span>
            </div>
          )}

          {/* Welcome message - improved */}
          {messages.length === 0 && !isLoading && (
            <div className="text-center mt-20 text-gray-500">
              <div className="text-6xl mb-4">🤗</div>
              <h1 className="text-3xl font-bold text-gray-800">Welcome to HUGG Chat!</h1>
              <p className="mt-2 text-gray-600">Start a conversation by typing a message below</p>
              <div className="mt-6 text-sm text-gray-500 space-y-1">
                <p>💡 Try asking: "What can you help me with?"</p>
                <p>💬 Or: "Tell me a fun fact"</p>
              </div>
            </div>
          )}

          {/* Messages */}
          {messages.map((msg, index) => (
            <Message key={`${msg.timestamp}-${index}`} message={msg} />
          ))}
          
          <div ref={messagesEndRef} />
        </div>
      </div>
      <PromptInput onSend={sendMessage} isLoading={isLoading} />
    </div>
  );
};