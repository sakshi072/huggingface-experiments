import { useState, useEffect, useCallback, useRef } from "react";
import { useUser } from "@clerk/clerk-react";
import type { ChatMessage, HistoryMessage } from "../types/chat-types";
import { chatService } from "../api/chat-service";
import { authChatService } from "../api/auth-service";
import type { ChatSessionMetadata } from "../api/auth-service";

const PAGE_SIZE = 10;

export const useChat = () => {
    const { user, isLoaded } = useUser();
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [currentChatId, setCurrentChatId] = useState<string | null>(null);
    const [chatSessions, setChatSessions] = useState<ChatSessionMetadata[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [isPaginating, setIsPaginating] = useState(false);
    const [hasMore, setHasMore] = useState(false);
    const isLoadingMoreRef = useRef(false);
    const hasInitializedRef = useRef(false); // Prevent double initialization
    
    const messagesLoadedFromHistoryRef = useRef(0);
    const messagesSentInSessionRef = useRef(0);

    // Load user's chat sessions when authenticated
    useEffect(() => {
        if (isLoaded && user?.id && !hasInitializedRef.current) {
            hasInitializedRef.current = true;
            initializeChats();
        }
    }, [isLoaded, user?.id]);

    const initializeChats = async () => {
        if (!user?.id) return;
        
        try {
            const sessions = await authChatService.getChatSession(user.id);
            setChatSessions(sessions.sort((a, b) => 
                new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            ));
            
            // Auto-select or create first chat
            if (sessions.length > 0) {
                // User has existing chats - select the most recent one
                setCurrentChatId(sessions[0].chat_id);
            } else {
                // New user - create their first chat automatically
                console.log("New user detected - creating first chat...");
                const newChat = await authChatService.createChatSession(user.id, "New Chat");
                setCurrentChatId(newChat.chat_id);
                
                // Refresh the session list
                const updatedSessions = await authChatService.getChatSession(user.id);
                setChatSessions(updatedSessions);
            }
        } catch (error) {
            console.error("Failed to initialize chats:", error);
            // Even on error, try to create a chat so user can start
            try {
                const newChat = await authChatService.createChatSession(user.id, "New Chat");
                setCurrentChatId(newChat.chat_id);
            } catch (createError) {
                console.error("Failed to create fallback chat:", createError);
            }
        }
    };

    const loadChatSessions = async () => {
        if (!user?.id) return;
        
        try {
            const sessions = await authChatService.getChatSession(user.id);
            setChatSessions(sessions.sort((a, b) => 
                new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            ));
        } catch (error) {
            console.error("Failed to load chat sessions:", error);
        }
    };

    const loadHistorySegment = useCallback(async () => {
        if (!user?.id || !currentChatId) return;
        if (isPaginating || isLoading || isLoadingMoreRef.current || !hasMore) return;

        isLoadingMoreRef.current = true;
        setIsPaginating(true);

        try {
            const offset = messagesLoadedFromHistoryRef.current + messagesSentInSessionRef.current;
            
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

            const clientMessages: ChatMessage[] = history.map(msg => ({
                ...msg,
                status: 'sent',
            }));

            setMessages(prev => {
                const existingTimestamps = new Set(prev.map(m => m.timestamp));
                const newUniqueMessages = clientMessages.filter(m => !existingTimestamps.has(m.timestamp));
                
                if (newUniqueMessages.length === 0) {
                    setHasMore(false);
                    return prev;
                }
                
                messagesLoadedFromHistoryRef.current += newUniqueMessages.length;
                return [...newUniqueMessages, ...prev];
            });

            if (history.length < PAGE_SIZE) {
                setHasMore(false);
            }
        } catch (error) {
            console.error("Failed to load history:", error);
        } finally {
            setIsPaginating(false);
            setTimeout(() => {
                isLoadingMoreRef.current = false;
            }, 500);
        }
    }, [user?.id, currentChatId, hasMore, isLoading, isPaginating]);

    // Load initial history when chat changes
    useEffect(() => {
        if (!user?.id || !currentChatId) return;

        setMessages([]);
        setHasMore(false);
        messagesLoadedFromHistoryRef.current = 0;
        messagesSentInSessionRef.current = 0;
        
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

                const clientMessages: ChatMessage[] = history.map(msg => ({
                    ...msg,
                    status: 'sent',
                }));

                setMessages(clientMessages);
                messagesLoadedFromHistoryRef.current = clientMessages.length;

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

        const newUserMessage: ChatMessage = {
            session_id: currentChatId,
            role: 'user',
            content: prompt,
            timestamp: new Date().toISOString(),
            status: 'sent',
        };

        const loadingAssistantMessage: ChatMessage = {
            session_id: currentChatId,
            role: 'assistant',
            content: 'Thinking...',
            timestamp: new Date().toISOString(),
            status: 'loading',
        };

        setMessages(prev => [...prev, newUserMessage, loadingAssistantMessage]);

        try {
            const response = await chatService.getInference(user.id, currentChatId, prompt);

            setMessages(prev => {
                const newMessages = [...prev];
                const lastMessageIndex = newMessages.length - 1;

                if (lastMessageIndex >= 0 && newMessages[lastMessageIndex].status === 'loading') {
                    newMessages[lastMessageIndex] = {
                        ...newMessages[lastMessageIndex],
                        content: response.response,
                        status: 'sent',
                        timestamp: new Date().toISOString(),
                    };
                }
                
                return newMessages;
            });

            messagesSentInSessionRef.current += 2;
            
            const totalMessages = messagesLoadedFromHistoryRef.current + messagesSentInSessionRef.current;
            if (totalMessages > PAGE_SIZE && !hasMore) {
                setHasMore(true);
            }

            // Refresh chat sessions to update timestamps/counts
            loadChatSessions();
        } catch (error) {
            console.error("Inference call failed:", error);
            setMessages(prev => {
                const newMessages = [...prev];
                const lastMessageIndex = newMessages.length - 1;
                newMessages[lastMessageIndex] = {
                    ...newMessages[lastMessageIndex],
                    content: 'Sorry, the AI encountered an error.',
                    status: 'error',
                    timestamp: new Date().toISOString(),
                };
                return newMessages;
            });
            
            messagesSentInSessionRef.current += 2;
        } finally {
            setIsLoading(false);
        }
    };

    const startNewChat = async () => {
        if (!user?.id) return;

        try {
            const newChat = await authChatService.createChatSession(user.id, "New Chat");
            setCurrentChatId(newChat.chat_id);
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
            
            // If we deleted the current chat, switch to another or create new
            if (chatId === currentChatId) {
                const remainingSessions = chatSessions.filter(s => s.chat_id !== chatId);
                if (remainingSessions.length > 0) {
                    setCurrentChatId(remainingSessions[0].chat_id);
                } else {
                    // No chats left - create a new one
                    await startNewChat();
                }
            }
            
            await loadChatSessions();
        } catch (error) {
            console.error("Failed to delete chat:", error);
        }
    };

    const loadPreviousMessages = useCallback(() => {
        loadHistorySegment();
    }, [loadHistorySegment]);

    return {
        messages,
        isLoading,
        isPaginating,
        hasMore,
        sendMessage,
        loadPreviousMessages,
        currentChatId,
        chatSessions,
        startNewChat,
        switchToChat,
        deleteChat,
        isAuthenticated: isLoaded && !!user,
    };
};