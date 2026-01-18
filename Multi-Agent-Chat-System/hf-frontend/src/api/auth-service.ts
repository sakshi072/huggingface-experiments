import apiClient from "./axios-instance";

export interface ChatSessionMetadata {
    chat_id: string;
    user_id: string;
    title: string;
    created_at: string;
    updated_at: string;
    message_count: number;
    last_message_preview?:string;

}

export interface CreateChatResponse {
    chat_id:string;
    title:string;
}

export interface ChatSessionResponse {
    sessions: ChatSessionMetadata[]
    next_cursor: string | null;
    has_more: boolean;
    total_count?: number;
}


export const authChatService = {
    /**
     * POST /chat/sessions - Create a new chat session
     */
    async createChatSession(title?:string): Promise<CreateChatResponse> {
        const response = await apiClient.post<CreateChatResponse>(
            '/chat/sessions',
            {title: title || 'New Chat'},
        );
        return response.data;
    },

    /**
     * GET /chat/sessions - Get chat sessions with CURSOR pagination
     * 
     * NEW: Uses cursor instead of offset
     * 
     * @param limit - Number of sessions to fetch (default: 20)
     * @param cursor - Pagination cursor (null for first page)
     * @returns Sessions, next cursor, and has_more flag
     */
    async getChatSession(
        limit: number = 10, 
        cursor: string | null = null
    ): Promise<ChatSessionResponse>{
        const params: any = { limit }
        if (cursor){
            params.cursor = cursor;
        }
        const response = await apiClient.get<ChatSessionResponse>(
            '/chat/sessions',
            {
                params
            }
        );
        return response.data;
    },

    /**
     * DELETE /chat/sessions/{chat_id} - Delete a specific chat session
     */

    async deleteChatSession(chatId:string): Promise<void> {
        await apiClient.delete(`/chat/sessions/${chatId}`);
    },

    /**
     * PATCH /chat/sessions/{chat_id}/title - Update chat title
     */
    async updateChatSession(chatId:string, title:string): Promise<void> {
        await apiClient.patch(
            `/chat/sessions/${chatId}/title`,
            {title}
        );
    }
};