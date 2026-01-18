export interface HistoryMessage {
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string; // ISO 8601 string from datetime
}

export interface InferenceResponse {
  response: string;
}

/**
* NEW: Updated to include cursor pagination fields
*/
export interface HistoryResponse {
  history: HistoryMessage[];
  next_cursor: string | null;
  has_more: boolean;
  total_count?: number;
}

// Client-side representation of a chat message
export interface ChatMessage extends HistoryMessage {
  // Add a status to handle loading states in the UI
  status: 'sent' | 'loading' | 'error';
}

export type ChatSession = string; // session_id is just a string