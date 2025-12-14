import apiClient from "./axios-instance";

export interface ChatSessionMetadata {
    chat_id: string;
    user_id: string;
    title: string;
    created_at: string;
    updated_at: string;
    message_count: number;
}

export interface CreateChatResponse {
    chat_id:string;
    title:string;
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
     * GET /chat/sessions - Get all chat sessions for a user
     */

    async getChatSession(limit: number = 10, offset: number = 0): Promise<ChatSessionMetadata[]>{
        const response = await apiClient.get<{ sessions: ChatSessionMetadata[]}>(
            '/chat/sessions',
            {
                params:{
                    limit: limit,
                    offset:offset
                }
            }
        );
        return response.data.sessions;
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