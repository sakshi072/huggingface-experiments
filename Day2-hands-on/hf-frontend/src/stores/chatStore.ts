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

  hasMoreSessions: boolean;
  sessionOffset: number;
  isLoadingSessions: boolean;
  
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
  
  setHasMoreSessions: (hasMore: boolean) => void;
  setSessionsOffset: (offset: number) => void;
  incrementSessionsOffset: (count: number) => void;
  setIsLoadingSessions: (loading: boolean) => void;
  resetSessionsPagination: () => void;

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

        hasMoreSessions: false,
        sessionOffset: 0,
        isLoadingSessions: false,
        
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
        
        // FIX: Set offset when setting sessions
        setChatSessions: (sessions) => set({ 
          chatSessions: sessions,
          sessionOffset: sessions.length  // Track how many we've loaded
        }),

        appendChatSessions: (sessions) => set((state) => {
            const existingIds = new Set(state.chatSessions.map(s=>s.chat_id));
            const newSessions = sessions.filter(s => !existingIds.has(s.chat_id))

            return {
                chatSessions: [...state.chatSessions, ...newSessions]
            }

        }),
        
        setIsLoading: (loading) => set({ isLoading: loading }),
        
        setIsPaginating: (paginating) => set({ isPaginating: paginating }),
        
        setHasMore: (hasMore) => set({ hasMore: hasMore }),

        setHasMoreSessions: (hasMore) => set({hasMoreSessions: hasMore}),

        setSessionsOffset: (session) => set({sessionOffset:session}),
        
        incrementSessionsOffset: (count) => set((state) => ({
            sessionOffset: state.sessionOffset + count
        })),
        
        setIsLoadingSessions:(loadingSession) => set({isLoadingSessions: loadingSession}),
        
        resetSessionsPagination: () => set({
            sessionOffset: 0,
            hasMoreSessions: false
        }),
        
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
          sessionOffset: 0,
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
          chatsTitled: Array.from(state.chatsTitled), // Convert Set to Array for storage
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