import { useEffect, useCallback, useRef } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { chatService } from "../api/chat-service";
import { authChatService } from "../api/auth-service";
import { smartTitleService } from "../api/smart-title-service";
import { useChatStore } from "../stores/chatStore";
import { useAuthStore } from "../stores/authStore";

const PAGE_SIZE = 20;
const SESSIONS_PAGE_SIZE = 20;

// GLOBAL singleton to prevent multiple simultaneous initializations
let globalInitPromise: Promise<void> | null = null;
let globalInitInProgress = false;
let lastInitUserId: string | null = null;

export const useChat = () => {
    const { isAuthenticated, isLoading, user } = useAuth0()
    const {
        messages,
        currentChatId,
        chatSessions,
        isLoading: chatIsLoading,
        isPaginating,
        hasMore,
        hasMoreSessions,
        sessionsCursor,
        messagesCursor,
        isLoadingSessions,
        messagesLoadedFromHistory,
        messagesSentInSession,
        setMessages,
        addMessage,
        updateLastMessage,
        setCurrentChatId,
        setChatSessions,
        appendChatSessions,
        setIsLoading,
        setIsPaginating,
        setHasMore,
        setHasMoreSessions,
        setSessionsCursor,
        setMessagesCursor,
        setIsLoadingSessions,
        resetSessionsPagination,
        incrementMessagesLoaded,
        incrementMessagesSent,
        markChatAsTitled,
        isChatTitled,
        unmarkChatAsTitled,
        resetMessages
    } = useChatStore();
    
    const {
        hasInitialized,
        setIsAuthenticated,
        setIsLoaded,
        setHasInitialized
    } = useAuthStore();

    const prevAuthState = useRef(isAuthenticated);

    // FIXED: Only ONE useEffect for auth state - removed duplicate
    useEffect(() => {
        setIsLoaded(!isLoading);
        setIsAuthenticated(isAuthenticated);
        
        // Reset on logout
        if (prevAuthState.current && !isAuthenticated) {
            console.log('[useChat] 🚪 User logged out - resetting state');
            useChatStore.getState().resetAllState();
            setHasInitialized(false);
            globalInitPromise = null;
            globalInitInProgress = false;
            lastInitUserId = null;
        }
        
        prevAuthState.current = isAuthenticated;
    }, [isLoading, isAuthenticated, setIsLoaded, setIsAuthenticated, setHasInitialized]);

    // FIXED: Initialize chats with global singleton guard
    useEffect(() => {
        const currentUserId = user?.sub || null;
        
        // Skip if conditions not met
        if (isLoading || !isAuthenticated || !currentUserId || hasInitialized) {
            return;
        }

        // If same user already initialized, skip
        if (lastInitUserId === currentUserId) {
            console.log('[useChat] ⏭️ Already initialized for this user');
            setHasInitialized(true);
            return;
        }

        // If initialization in progress, wait for it
        if (globalInitInProgress) {
            console.log('[useChat] ⏳ Initialization in progress, waiting...');
            if (globalInitPromise) {
                globalInitPromise.then(() => {
                    setHasInitialized(true);
                });
            }
            return;
        }

        // Start initialization
        globalInitInProgress = true;
        lastInitUserId = currentUserId;
        setHasInitialized(true);
        
        globalInitPromise = initializeChats()
            .catch((error) => {
                setHasInitialized(false);
                globalInitInProgress = false;
                lastInitUserId = null;
            })
            .finally(() => {
                globalInitInProgress = false;
                setTimeout(() => {
                    globalInitPromise = null;
                }, 1000);
            });
            
    }, [isLoading, isAuthenticated, hasInitialized, user, setHasInitialized]);

    const initializeChats = async () => {
        try {
            const response = await authChatService.getChatSession(SESSIONS_PAGE_SIZE, null);
            
            const sortedSessions = response.sessions.sort((a, b) => 
                new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            );
            
            setChatSessions(sortedSessions);
            setHasMoreSessions(response.has_more);
            setSessionsCursor(response.next_cursor);

            // Mark titled sessions
            sortedSessions.forEach(session => {
                if(session.title !== 'New Chat'){
                    markChatAsTitled(session.chat_id);
                }
            });

            if (sortedSessions.length > 0) {
                setCurrentChatId(sortedSessions[0].chat_id);
            } else {
                const newChat = await authChatService.createChatSession("New Chat");
                setCurrentChatId(newChat.chat_id);
                
                // Add to local state immediately
                const newSession = {
                    chat_id: newChat.chat_id,
                    user_id: user?.sub || '',
                    title: newChat.title,
                    created_at: new Date().toISOString(),
                    updated_at: new Date().toISOString(),
                    message_count: 0
                };
                setChatSessions([newSession]);
                
                // Refresh from server
                setTimeout(async () => {
                    const updated = await authChatService.getChatSession(SESSIONS_PAGE_SIZE, null);
                    setChatSessions(updated.sessions);
                    setHasMoreSessions(updated.has_more);
                    setSessionsCursor(updated.next_cursor);
                }, 300);
            }
        } catch (error) {
            console.error("[useChat] ❌ Init failed:", error);
            throw error;
        }
    };

    const loadChatSessions = async () => {
        try {
            const response = await authChatService.getChatSession(SESSIONS_PAGE_SIZE, 0);
            setChatSessions(response.sessions.sort((a, b) => 
                new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            ));
            setHasMoreSessions(response.has_more);
            setSessionsCursor(response.next_cursor);
        } catch (error) {
            console.error("Failed to load chat sessions:", error);
        }
    };

    const loadMoreSessions = useCallback(async () => {
        if (isLoadingSessions || !hasMoreSessions || ! sessionsCursor) {
            return;
        }

        console.log('[useChat] Loading more sessions with cursor:', sessionsCursor);
        setIsLoadingSessions(true);

        try {
            const response = await authChatService.getChatSession(
                SESSIONS_PAGE_SIZE,
                sessionsCursor
            );

            console.log('Loaded sessions:', response.sessions.length);

            if (response.sessions.length === 0) {
                setHasMoreSessions(false);
                return;
            }

            const sortedSession = response.sessions.sort((a,b) => 
                new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            );

            appendChatSessions(sortedSession);
            setSessionsCursor(response.next_cursor);  
            setHasMoreSessions(response.has_more);

            sortedSession.forEach(session => {
                if(session.title !== 'New Chat') {
                    markChatAsTitled(session.chat_id)
                }
            });
        } catch (error) {
            console.error("Failed to load more sessions:", error);
        } finally {
            setIsLoadingSessions(false);
        }

    }, [
        sessionsCursor, 
        isLoadingSessions, 
        hasMoreSessions,
        appendChatSessions,
        setSessionsCursor,
        markChatAsTitled,
        setHasMoreSessions,
        setIsLoadingSessions
    ]);

    const loadHistorySegment = useCallback(async () => {
        if (!currentChatId || isPaginating || chatIsLoading || !hasMore) return;

        setIsPaginating(true);

        try {
            
            const response = await chatService.getHistory(
                currentChatId,
                PAGE_SIZE,
                messagesCursor
            );

            if (response.history.length === 0) {
                setHasMore(false);
                return;
            }

            const clientMessages = response.history.map(msg => ({
                ...msg,
                status: 'sent' as const,
            }));

            const existingTimestamps = new Set(messages.map(m => m.timestamp));
            const newUniqueMessages = clientMessages.filter(m => !existingTimestamps.has(m.timestamp));

            if (newUniqueMessages.length === 0){
                setHasMore(false);
                return;
            }

            incrementMessagesLoaded(newUniqueMessages.length);
            setMessages([...newUniqueMessages, ...messages]);

            setMessagesCursor(response.next_cursor);
            setHasMore(response.has_more);
        } catch (error) {
            console.error("Failed to load history:", error);
        } finally {
            setIsPaginating(false);
        }
    }, [
        currentChatId, 
        hasMore, 
        chatIsLoading, 
        isPaginating,
        messagesCursor,
        messages,
        incrementMessagesLoaded,
        setMessages,
        setMessagesCursor,
        setHasMore,
        setIsPaginating
    ]);

    // Load initial history when chat changes
    useEffect(() => {
        if (!currentChatId) return;

        console.log(`[useChat] 💬 Chat changed to: ${currentChatId.slice(0,8)}`);
        resetMessages();
        
        const loadInitial = async () => {
            setIsLoading(true);
            try {
                const response = await chatService.getHistory(
                    currentChatId,
                    PAGE_SIZE,
                    null
                );

                if (response.history.length === 0) return;

                const clientMessages = response.history.map(msg => ({
                    ...msg,
                    status: 'sent' as const,
                }));

                setMessages(clientMessages);
                incrementMessagesLoaded(clientMessages.length);

                setMessagesCursor(response.next_cursor);
                setHasMore(response.has_more);
            } catch (error: any) {
                console.error("Failed to load initial history:", error);
                
                // Handle 403 - user doesn't own this chat
                if (error?.response?.status === 403) {
                    console.warn('[useChat] ⚠️ 403 error - creating new chat');
                    await startNewChat();
                }
            } finally {
                setIsLoading(false);
            }
        };

        loadInitial();
    }, [currentChatId]);

    const sendMessage = async (prompt: string) => {
        if (!currentChatId || !prompt.trim() || chatIsLoading) return;

        setIsLoading(true);

        const newUserMessage = {
            session_id: currentChatId,
            role: 'user' as const,
            content: prompt,
            timestamp: new Date().toISOString(),
            status: 'sent' as const,
        };

        const loadingAssistantMessage = {
            session_id: currentChatId,
            role: 'assistant' as const,
            content: 'Thinking...' as const,
            timestamp: new Date().toISOString(),
            status: 'loading' as const,
        };

        addMessage(newUserMessage);
        addMessage(loadingAssistantMessage)

        try {
            const response = await chatService.getInference(currentChatId, prompt);

            updateLastMessage(response.response, 'sent');
            incrementMessagesSent(2);
            
            const totalMessages = messagesLoadedFromHistory + messagesSentInSession + 2;
            if (totalMessages > PAGE_SIZE && !hasMore) {
                setHasMore(true);
            }

            const shouldAutoTitle = !isChatTitled(currentChatId);
            if(shouldAutoTitle){
                const currentChat = chatSessions.find(s => s.chat_id === currentChatId);
                if (currentChat && currentChat.title === 'New Chat' && currentChat.message_count===0){
                    smartTitleService.generateTitle(prompt, response.response)
                        .then(async (titleResult) => {
                            try {
                                await authChatService.updateChatSession(currentChatId, titleResult.title);
                                markChatAsTitled(currentChatId);

                                console.log(titleResult.fallback 
                                    ? `Used fallback title: "${titleResult.title}"`
                                    : `AI-generated title: "${titleResult.title}"`
                                );
                                
                                loadChatSessions();
                            } catch (error) {
                                console.error("Failed to save AI-generated title:", error);
                            }
                        })
                        .catch((error) => {
                            console.error("Failed to generate AI title:", error);
                        });
                }
            }

            loadChatSessions();
        } catch (error) {
            console.error("Inference call failed:", error);
            updateLastMessage('Sorry, the AI encountered an error.', 'error');
            incrementMessagesSent(2);
        } finally {
            setIsLoading(false);
        }
    };

    const startNewChat = async () => {
        try {
            const newChat = await authChatService.createChatSession("New Chat");
            setCurrentChatId(newChat.chat_id);

            resetSessionsPagination();
            await loadChatSessions();
        } catch (error) {
            console.error("Failed to create new chat:", error);
        }
    };

    const switchToChat = (chatId: string) => {
        console.log(`[useChat] 🔄 Switching to: ${chatId.slice(0,8)}`);
        setCurrentChatId(chatId);
    };

    const deleteChat = async (chatId: string) => {
        try {
            await authChatService.deleteChatSession(chatId);
            unmarkChatAsTitled(chatId);
            
            if (chatId === currentChatId) {
                const remainingSessions = chatSessions.filter(s => s.chat_id !== chatId);
                if (remainingSessions.length > 0) {
                    setCurrentChatId(remainingSessions[0].chat_id);
                } else {
                    await startNewChat();
                }
            }
            
            resetSessionsPagination();
            await loadChatSessions();
        } catch (error) {
            console.error("Failed to delete chat:", error);
        }
    };

    const updateChatTitle = async (chatId:string, newTitle:string) => {
        try {
            await authChatService.updateChatSession(chatId, newTitle);
            markChatAsTitled(chatId);
            await loadChatSessions();
        } catch (error) {
            console.error("Failed to update chat title", error);
        }
    };

    const loadPreviousMessages = useCallback(() => {
        loadHistorySegment();
    }, [loadHistorySegment]);

    return {
        sendMessage,
        loadPreviousMessages,
        loadMoreSessions,
        hasMoreSessions,
        startNewChat,
        switchToChat,
        deleteChat,
        updateChatTitle,
        isAuthenticated: isAuthenticated,
    };
};