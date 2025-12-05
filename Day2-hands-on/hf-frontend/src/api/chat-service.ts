import axios from "axios";
import type { HistoryMessage, InferenceResponse, HistoryResponse } from '../types/chat-types';

const API_BASE_URL = 'http://127.0.0.1:8000';
const API = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    }
});

export const chatService = {
    /**
     * POST /chat/prompt - Sends the user prompt and receives the LLM response.
     * Now requires both user_id and chat_id
     */
    async getInference(userId: string, chatId: string, prompt: string): Promise<InferenceResponse> {
        const response = await API.post<InferenceResponse>(
            '/chat/prompt',
            { prompt },
            {
                headers: {
                    'user-id': userId,
                    'chat-id': chatId,
                }
            }
        );
        return response.data;
    },

    /**
     * GET /chat/history - Retrieves the chat history for a specific chat.
     */
    async getHistory(userId: string, chatId: string, limit: number, offset: number): Promise<HistoryMessage[]> {
        if (!userId || !chatId) return [];

        const response = await API.get<HistoryResponse>('/chat/history', {
            params: {
                chat_id: chatId,
                limit: limit,
                offset: offset
            },
            headers: {
                'user-id': userId,
            }
        });
        
        return response.data.history;
    },

    /**
     * DELETE /chat/history/clear - Clears the chat history for a specific chat.
     */
    async clearHistory(userId: string, chatId: string): Promise<void> {
        if (!userId || !chatId) return;
        
        await API.delete('/chat/history/clear', {
            params: { chat_id: chatId },
            headers: {
                'user-id': userId,
            }
        });
    },
};