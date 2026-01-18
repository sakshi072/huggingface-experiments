import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type { ChatMessage } from '../types/chat-types';
import type { ChatSessionMetadata } from '../api/auth-service';

interface ChatState {
  // Current chat state
  messages: ChatMessage[];
  currentChatId: string | null;
  chatSessions: ChatSessionMetadata[];
  
  // Loading states
  isLoading: boolean;
  isPaginating: boolean;
  hasMore: boolean;

  // CHANGED: Cursor-based pagination for sessions
  hasMoreSessions: boolean;
  sessionsCursor: string | null;  // CHANGED: from sessionOffset to cursor
  isLoadingSessions: boolean;

  // CHANGED: Cursor-based pagination for messages
  messagesCursor: string | null;  // NEW: Track current cursor for messages
  
  // Pagination tracking
  messagesLoadedFromHistory: number;
  messagesSentInSession: number;
  
  // Titled chats tracking
  chatsTitled: Set<string>;
  
  // Actions
  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (message: ChatMessage) => void;
  updateLastMessage: (content: string, status: 'sent' | 'loading' | 'error') => void;
  
  setCurrentChatId: (chatId: string | null) => void;
  setChatSessions: (sessions: ChatSessionMetadata[]) => void;
  appendChatSessions: (sessions: ChatSessionMetadata[]) => void;
  
  // CHANGED: Cursor-based methods
  setHasMoreSessions: (hasMore: boolean) => void;
  setSessionsCursor: (cursor: string | null) => void;  // CHANGED
  setIsLoadingSessions: (loading: boolean) => void;
  resetSessionsPagination: () => void;

  // NEW: Message cursor methods
  setMessagesCursor: (cursor: string | null) => void;

  setIsLoading: (loading: boolean) => void;
  setIsPaginating: (paginating: boolean) => void;
  setHasMore: (hasMore: boolean) => void;
  
  incrementMessagesLoaded: (count: number) => void;
  incrementMessagesSent: (count: number) => void;
  resetPaginationTracking: () => void;
  
  markChatAsTitled: (chatId: string) => void;
  isChatTitled: (chatId: string) => boolean;
  unmarkChatAsTitled: (chatId: string) => void;
  
  // Reset functions
  resetMessages: () => void;
  resetAllState: () => void;
}

export const useChatStore = create<ChatState>()(
  devtools(
    persist(
      (set, get) => ({
        // Initial state
        messages: [],
        currentChatId: null,
        chatSessions: [],
        
        isLoading: false,
        isPaginating: false,
        hasMore: false,

        // CHANGED: Cursor instead of offset
        hasMoreSessions: false,
        sessionsCursor: null,  // CHANGED
        isLoadingSessions: false,

        // NEW: Message cursor
        messagesCursor: null,
        
        messagesLoadedFromHistory: 0,
        messagesSentInSession: 0,
        
        chatsTitled: new Set<string>(),
        
        // Actions
        setMessages: (messages) => set({ messages }),
        
        addMessage: (message) => set((state) => ({
          messages: [...state.messages, message]
        })),
        
        updateLastMessage: (content, status) => set((state) => {
          const newMessages = [...state.messages];
          const lastIndex = newMessages.length - 1;
          
          if (lastIndex >= 0) {
            newMessages[lastIndex] = {
              ...newMessages[lastIndex],
              content,
              status,
              timestamp: new Date().toISOString(),
            };
          }
          
          return { messages: newMessages };
        }),
        
        setCurrentChatId: (chatId) => set({ currentChatId: chatId }),
        
        // CHANGED: Set cursor to null when setting initial sessions
        setChatSessions: (sessions) => set({ 
          chatSessions: sessions,
          sessionsCursor: null  // Reset cursor
        }),

        appendChatSessions: (sessions) => set((state) => {
          const existingIds = new Set(state.chatSessions.map(s => s.chat_id));
          const newSessions = sessions.filter(s => !existingIds.has(s.chat_id));

          return {
            chatSessions: [...state.chatSessions, ...newSessions]
          };
        }),
        
        setIsLoading: (loading) => set({ isLoading: loading }),
        
        setIsPaginating: (paginating) => set({ isPaginating: paginating }),
        
        setHasMore: (hasMore) => set({ hasMore: hasMore }),

        setHasMoreSessions: (hasMore) => set({ hasMoreSessions: hasMore }),

        // CHANGED: Set cursor instead of offset
        setSessionsCursor: (cursor) => set({ sessionsCursor: cursor }),
        
        setIsLoadingSessions: (loadingSession) => set({ isLoadingSessions: loadingSession }),
        
        // CHANGED: Reset cursor
        resetSessionsPagination: () => set({
          sessionsCursor: null,
          hasMoreSessions: false
        }),

        // NEW: Message cursor methods
        setMessagesCursor: (cursor) => set({ messagesCursor: cursor }),
        
        incrementMessagesLoaded: (count) => set((state) => ({
          messagesLoadedFromHistory: state.messagesLoadedFromHistory + count
        })),
        
        incrementMessagesSent: (count) => set((state) => ({
          messagesSentInSession: state.messagesSentInSession + count
        })),
        
        resetPaginationTracking: () => set({
          messagesLoadedFromHistory: 0,
          messagesSentInSession: 0,
        }),
        
        markChatAsTitled: (chatId) => set((state) => ({
          chatsTitled: new Set([...state.chatsTitled, chatId])
        })),
        
        isChatTitled: (chatId) => get().chatsTitled.has(chatId),
        
        unmarkChatAsTitled: (chatId) => set((state) => {
          const newSet = new Set(state.chatsTitled);
          newSet.delete(chatId);
          return { chatsTitled: newSet };
        }),
        
        resetMessages: () => set({
          messages: [],
          hasMore: false,
          messagesCursor: null,  // NEW: Reset cursor
          messagesLoadedFromHistory: 0,
          messagesSentInSession: 0,
        }),
        
        resetAllState: () => set({
          messages: [],
          currentChatId: null,
          chatSessions: [],
          isLoading: false,
          isPaginating: false,
          hasMore: false,
          sessionsCursor: null,  // CHANGED
          messagesCursor: null,  // NEW
          hasMoreSessions: false,
          isLoadingSessions: false,
          messagesLoadedFromHistory: 0,
          messagesSentInSession: 0,
          chatsTitled: new Set<string>(),
        }),
      }),
      {
        name: 'chat-storage',
        // Only persist certain fields
        partialize: (state) => ({
          currentChatId: state.currentChatId,
          chatsTitled: Array.from(state.chatsTitled),
        }),
        // Hydrate Set from Array
        onRehydrateStorage: () => (state) => {
          if (state && Array.isArray((state as any).chatsTitled)) {
            state.chatsTitled = new Set((state as any).chatsTitled);
          }
        },
      }
    ),
    { name: 'ChatStore' }
  )
);