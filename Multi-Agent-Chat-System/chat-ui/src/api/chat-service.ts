import apiClient from './axios-instance';
import type { HistoryMessage, InferenceResponse, HistoryResponse } from '../types/chat-types';

export const chatService = {
    /**
     * POST /chat/prompt - Sends the user prompt and receives the LLM response.
     * Now requires both user_id and chat_id
     */
    async getInference(chatId: string, prompt: string): Promise<InferenceResponse> {
        const response = await apiClient.post<InferenceResponse>(
            '/chat/prompt',
            { prompt },
            {
                headers: {
                    'chat-id': chatId,
                }
            }
        );
        return response.data;
    },

    /**
     * GET /chat/history - Retrieves chat history with CURSOR pagination
     * 
     * NEW: Uses cursor instead of offset
     * 
     * @param chatId - The chat session ID
     * @param limit - Number of messages to fetch
     * @param cursor - Pagination cursor (null for first page)
     * @returns History messages, next cursor, and has_more flag
     */
    async getHistory(
        chatId: string, 
        limit: number, 
        cursor: string | null = null
    ): Promise<HistoryResponse> {
        if (!chatId) {
            return {
                history:[],
                next_cursor:null,
                has_more:false
            }
        }

        const params: any = {
            chat_id:chatId,
            limit:limit
        }

        if (cursor) {
            params.cursor = cursor;
        }

        const response = await apiClient.get<HistoryResponse>('/chat/history', {
            params
        });
        
        return response.data;
    },

    /**
     * DELETE /chat/history/clear - Clears the chat history for a specific chat.
     */
    async clearHistory(chatId: string): Promise<void> {
        if (!chatId) return;
        
        await apiClient.delete('/chat/history/clear', {
            params: { chat_id: chatId },
        });
    },
};