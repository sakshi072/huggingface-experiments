import axios from "axios";

const API_BASE_URL = 'http://127.0.0.1:8000';

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

const API = axios.create({
    baseURL:API_BASE_URL,
    headers:{
        'Content-Type' : 'application/json',
    }
});

export const authChatService = {
    /**
     * POST /chat/sessions - Create a new chat session
     */
    async createChatSession(userId:string, title?:string): Promise<CreateChatResponse> {
        const response = await API.post<CreateChatResponse>(
            '/chat/sessions',
            {title: title || 'New Chat'},
            {
                headers:{
                    'user-id':userId
                }
            }
        );
        return response.data;
    },

    /**
     * GET /chat/sessions - Get all chat sessions for a user
     */

    async getChatSession(userId:string): Promise<ChatSessionMetadata[]>{
        const response = await API.get<{ sessions: ChatSessionMetadata[]}>(
            '/chat/sessions',
            {
                headers: {
                    'user-id': userId,
                }
            }
        );
        return response.data.sessions;
    },

    /**
     * DELETE /chat/sessions/{chat_id} - Delete a specific chat session
     */

    async deleteChatSession(userId:string, chatId:string): Promise<void> {
        await API.delete(`/chat/sessions/${chatId}`,{
            headers:{
                'user-id':userId,
            }
        });
    },

    /**
     * PATCH /chat/sessions/{chat_id}/title - Update chat title
     */
    async updateChatSession(userId:string, chatId:string, title:string): Promise<void> {
        await API.patch(
            `/chat/sessions/${chatId}/title`,
            {title},
            {
                headers:{
                    'user-id': userId,
                }
            }
        );
    }
};