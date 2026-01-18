import apiClient from "./axios-instance";

export interface GenerateTitleRequest {
    first_message: string;
    assistant_message: string
}

export interface GenerateTitleResponse {
    title: string;
    fallback: boolean;
}

export const smartTitleService = {
    /**
     * POST /chat/generate-title - Generate a smart title using AI
     * @param firstMessage The first user message in the conversation
     * @param assistantResponse Optional: The assistant's response for more context
     */

    async generateTitle(
        firstMessage: string,
        assistantResponse: string
    ): Promise<GenerateTitleResponse> {
        try {
            const response = await apiClient.post<GenerateTitleResponse>(
                '/chat/generate-title',
                {
                    first_message: firstMessage,
                    assistant_message: assistantResponse
                },
                {
                    timeout: 10000,
                }
            );
            return response.data
        } catch (error) {
            console.error("AI title generation failed:", error);
            return {
                title: generateFallbackTitle(firstMessage),
                fallback:true
            }
        }
    }
};

function generateFallbackTitle(message: string): string {
    
    // remove extra space
    const cleaned = message.trim().replace(/\s+/g, ' ');
    if (cleaned.length <= 50){
        return cleaned
    }

    const truncated = cleaned.substring(0,47);
    const lastSpace = truncated.lastIndexOf(' ');

    if (lastSpace > 30) {
        return truncated.substring(0, lastSpace) + '...';
    }

    return truncated + '...';
}