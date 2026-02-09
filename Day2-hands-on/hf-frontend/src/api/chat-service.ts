import apiClient from './axios-instance';
import type { HistoryMessage, InferenceResponse, HistoryResponse } from '../types/chat-types';
import { TOKEN_STORAGE_KEYS } from '../config/auth0-config';

export const chatService = {
    /**
     * POST /chat/prompt - Sends the user prompt and receives the LLM response.
     * Now requires both user_id and chat_id
     */

    async streamInference(
        chatId: string,
        prompt: string,
        onChunk: (text:string)=> void,
        onStatusUpdate? : (toolName: string) => void,
        onDone?: () => void
    ): Promise<string> {
        
        const baseURL = apiClient.defaults.baseURL
        const token = sessionStorage.getItem(TOKEN_STORAGE_KEYS.ACCESS_TOKEN)

        const response = await fetch(`${baseURL}/chat/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'chat-id': chatId,
                ...(token ? {'Authorization': `Bearer ${token}`}: {}),
            },
            body: JSON.stringify({prompt})
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        
        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let fullResponse = '';

        while(true) {
            const { done, value } = await reader.read();
            if (done) break;

            const text = decoder.decode(value, { stream:true });
            const lines = text.split('\n\n');

            for (const line of lines){
                if (!line.startsWith('data: ')) continue;
                try {
                    const raw = line.slice(6);
                    const payload = JSON.parse(raw)

                    switch(payload.type) {
                        case "status":
                            onStatusUpdate?.(payload.content);
                            break;
                        
                            case "token":
                                const text = payload.content;
                                fullResponse += text
                                onChunk(text);
                                onStatusUpdate?.("");
                                break;
                            case "error":
                                console.error("Bakcend Error:", payload.content);
                                onStatusUpdate?.(`Error: ${payload.content}`)
                    }    
                } catch (e) {
                    console.error("Error parsing SSE JSON:", e, "Line:", line)
                }
            }
        }
        onDone?.();
        return fullResponse
    },

    async getInference(chatId: string, prompt: string): Promise<InferenceResponse> {
        const response = await apiClient.post<InferenceResponse>(
            '/chat',
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