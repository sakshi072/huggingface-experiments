import { useEffect, useCallback } from "react";
import { useUser } from "@clerk/clerk-react";
import type { HistoryMessage } from "../types/chat-types";
import { chatService } from "../api/chat-service";
import { authChatService } from "../api/auth-service";
import { smartTitleService } from "../api/smart-title-service";
import { useChatStore } from "../stores/chatStore";
import { useAuthStore } from "../stores/authStore";

const PAGE_SIZE = 10;
const SESSIONS_PAGE_SIZE = 20;

export const useChat = () => {
    const { user, isLoaded } = useUser();
    const {
        messages,
        currentChatId,
        chatSessions,
        isLoading,
        isPaginating,
        hasMore,
        hasMoreSessions,
        sessionOffset,
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
        incrementSessionsOffset,
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
        setUserId,
        setIsAuthenticated,
        setIsLoaded,
        setHasInitialized
    } = useAuthStore();

    // Load user's chat sessions when authenticated
    useEffect(() => {
        setIsLoaded(isLoaded);
        setIsAuthenticated(isLoaded && !!user);
        if(user?.id){
            setUserId(user.id);
        }
    }, [isLoaded, user, setIsLoaded, setIsAuthenticated, setUserId]);

    // Initialize chats when authenticated
    useEffect(() => {
        if (isLoaded && user?.id && !hasInitialized) {
            setHasInitialized(true);
            initializeChats();
        }
    }, [isLoaded, user?.id, hasInitialized, setHasInitialized]);

    const initializeChats = async () => {
        if (!user?.id) return;
        
        try {
            // FIX: Pass limit and offset parameters
            const sessions = await authChatService.getChatSession(user.id, SESSIONS_PAGE_SIZE, 0);
            const sortedSessions = sessions.sort((a, b) => 
                new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            );
            
            setChatSessions(sortedSessions);
            // Set hasMoreSessions if we got a full page
            setHasMoreSessions(sessions.length === SESSIONS_PAGE_SIZE);

            // Auto-select or create first chat
            if (sortedSessions.length > 0) {
                setCurrentChatId(sortedSessions[0].chat_id);

                sortedSessions.forEach(session => {
                    if(session.title !=='New Chat'){
                        markChatAsTitled(session.chat_id);
                    }
                });
            } else {
                console.log("New user detected - creating first chat...");
                const newChat = await authChatService.createChatSession(user.id, "New Chat");
                setCurrentChatId(newChat.chat_id);
                
                // Refresh the session list
                const updatedSessions = await authChatService.getChatSession(user.id, SESSIONS_PAGE_SIZE, 0);
                setChatSessions(updatedSessions);
            }
        } catch (error) {
            console.error("Failed to initialize chats:", error);
            try {
                const newChat = await authChatService.createChatSession(user.id, "New Chat");
                setCurrentChatId(newChat.chat_id);
                await loadChatSessions();
            } catch (createError) {
                console.error("Failed to create fallback chat:", createError);
            }
        }
    };

    const loadChatSessions = async () => {
        if (!user?.id) return;
        
        try {
            // FIX: Pass limit and offset parameters
            const sessions = await authChatService.getChatSession(user.id, SESSIONS_PAGE_SIZE, 0);
            setChatSessions(sessions.sort((a, b) => 
                new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            ));
            setHasMoreSessions(sessions.length === SESSIONS_PAGE_SIZE);
        } catch (error) {
            console.error("Failed to load chat sessions:", error);
        }
    };

    const loadMoreSessions = useCallback(async () => {
        if (!user?.id || isLoadingSessions || !hasMoreSessions) {
            console.log('loadMoreSessions early return:', { 
                hasUser: !!user?.id, 
                isLoadingSessions, 
                hasMoreSessions 
            });
            return;
        }

        console.log('Loading more sessions, offset:', sessionOffset);
        setIsLoadingSessions(true);

        try {
            const sessions = await authChatService.getChatSession(
                user.id,
                SESSIONS_PAGE_SIZE,
                sessionOffset
            );

            console.log('Loaded sessions:', sessions.length);

            if (sessions.length === 0) {
                console.log('No more sessions to load');
                setHasMoreSessions(false);
                return;
            }

            const sortedSession = sessions.sort((a,b) => 
                new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            );

            appendChatSessions(sortedSession);
            incrementSessionsOffset(sortedSession.length);

            sortedSession.forEach(session => {
                if(session.title !== 'New Chat') {
                    markChatAsTitled(session.chat_id)
                }
            });

            if(sessions.length < SESSIONS_PAGE_SIZE){
                console.log('Loaded last page of sessions');
                setHasMoreSessions(false);
            }
        } catch (error) {
            console.error("Failed to load more sessions:", error);
        } finally {
            setIsLoadingSessions(false);
        }

    }, [
        user?.id, 
        sessionOffset, 
        isLoadingSessions, 
        hasMoreSessions,
        appendChatSessions,
        incrementSessionsOffset,
        markChatAsTitled,
        setHasMoreSessions,
        setIsLoadingSessions
    ]); // FIX: Added all dependencies

    const loadHistorySegment = useCallback(async () => {
        if (!user?.id || !currentChatId) return;
        if (isPaginating || isLoading || !hasMore) return;

        setIsPaginating(true);

        try {
            const offset = messagesLoadedFromHistory + messagesSentInSession;
            
            const history: HistoryMessage[] = await chatService.getHistory(
                user.id,
                currentChatId,
                PAGE_SIZE,
                offset
            );

            if (history.length === 0) {
                setHasMore(false);
                return;
            }

            const clientMessages = history.map(msg => ({
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

            if (history.length < PAGE_SIZE) {
                setHasMore(false);
            }
        } catch (error) {
            console.error("Failed to load history:", error);
        } finally {
            setIsPaginating(false);
        }
    }, [user?.id, currentChatId, hasMore, isLoading, isPaginating]);

    // Load initial history when chat changes
    useEffect(() => {
        if (!user?.id || !currentChatId) return;

        resetMessages();
        
        const loadInitial = async () => {
            setIsLoading(true);
            try {
                const history: HistoryMessage[] = await chatService.getHistory(
                    user.id,
                    currentChatId,
                    PAGE_SIZE,
                    0
                );

                if (history.length === 0) return;

                const clientMessages = history.map(msg => ({
                    ...msg,
                    status: 'sent' as const,
                }));

                setMessages(clientMessages);
                incrementMessagesLoaded(clientMessages.length);

                if (history.length >= PAGE_SIZE) {
                    setHasMore(true);
                }
            } catch (error) {
                console.error("Failed to load initial history:", error);
            } finally {
                setIsLoading(false);
            }
        };

        loadInitial();
    }, [user?.id, currentChatId]);

    const sendMessage = async (prompt: string) => {
        if (!user?.id || !currentChatId || !prompt.trim() || isLoading) return;

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
            const response = await chatService.getInference(user.id, currentChatId, prompt);

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
                    smartTitleService.generateTitle(user.id, prompt, response.response)
                        .then(async (titleResult) => {
                            try {
                                await authChatService.updateChatSession(user.id, currentChatId, titleResult.title);
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
        if (!user?.id) return;

        try {
            const newChat = await authChatService.createChatSession(user.id, "New Chat");
            setCurrentChatId(newChat.chat_id);

            resetSessionsPagination();
            await loadChatSessions();
        } catch (error) {
            console.error("Failed to create new chat:", error);
        }
    };

    const switchToChat = (chatId: string) => {
        setCurrentChatId(chatId);
    };

    const deleteChat = async (chatId: string) => {
        if (!user?.id) return;

        try {
            await authChatService.deleteChatSession(user.id, chatId);
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
        if(!user?.id) return;

        try {
            await authChatService.updateChatSession(user.id, chatId, newTitle);
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
        isAuthenticated: isLoaded && !!user,
    };
};