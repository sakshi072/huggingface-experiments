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
     * GET /chat/history - Retrieves the chat history for a specific chat.
     */
    async getHistory(chatId: string, limit: number, offset: number): Promise<HistoryMessage[]> {
        if (!chatId) return [];

        const response = await apiClient.get<HistoryResponse>('/chat/history', {
            params: {
                chat_id: chatId,
                limit: limit,
                offset: offset
            },
        });
        
        return response.data.history;
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