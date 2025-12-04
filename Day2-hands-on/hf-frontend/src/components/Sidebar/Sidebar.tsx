import React, {useState} from "react";
import type { ChatSessionMetadata } from "../../api/auth-service";

interface SidebarProps {
    chatSessions: ChatSessionMetadata[];
    currentChatId: string | null;
    onNewChat: () => void;
    onSelectChat: (chatId: string) => void;
    onDeleteChat: (chatId:string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
    chatSessions, 
    currentChatId,
    onNewChat,
    onSelectChat,
    onDeleteChat
}) => {
    const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
    
    const formatDate = (dateString:string) => {
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffDays = Math.floor(diffMs/(1000 * 60 * 60 * 24));

        if(diffDays === 0) return 'Today';
        if(diffDays === 1) return 'Yesterday';
        if(diffDays < 7) return `${diffDays} days ago`;
        return date.toLocaleDateString();
    };

    const handleDelete = (e: React.MouseEvent, chatId:string) => {
        e.stopPropagation();
        if(deleteConfirm === chatId){
            onDeleteChat(chatId);
            setDeleteConfirm(null);
        } else {
            setDeleteConfirm(chatId);
            setTimeout(() => setDeleteConfirm(null), 3000)
        }
    };

    return (
        <div className="w-full lg:w-80 bg-gray-900 text-white flex flex-col fixed inset-y-0 left-0 p-4 border-r border-gray-700 z-20">
          <h2 className="text-xl font-bold mb-6">🤗 HUGG Chat</h2>
          
          <button 
            onClick={onNewChat} 
            className="w-full py-2 px-4 mb-4 border border-gray-600 rounded-lg hover:bg-gray-700 transition-colors flex items-center justify-center gap-2"
          >
            <span>➕</span>
            <span>New Chat</span>
          </button>
    
          <div className="flex-grow overflow-y-auto scrollbar-thin scrollbar-thumb-gray-600">
            {chatSessions.length === 0 ? (
              <div className="text-center text-gray-400 mt-8">
                <p className="text-sm">No chats yet</p>
                <p className="text-xs mt-2">Start a new conversation!</p>
              </div>
            ) : (
              <div className="space-y-2">
                {chatSessions.map((session) => (
                  <div
                    key={session.chat_id}
                    onClick={() => onSelectChat(session.chat_id)}
                    className={`p-3 rounded-lg cursor-pointer transition-colors group ${
                      currentChatId === session.chat_id
                        ? 'bg-gray-700 border border-gray-600'
                        : 'hover:bg-gray-800'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-grow min-w-0">
                        <p className="font-medium truncate text-sm">
                          {session.title || 'Untitled Chat'}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-gray-400">
                            {formatDate(session.updated_at)}
                          </span>
                          <span className="text-xs text-gray-500">
                            • {session.message_count} msgs
                          </span>
                        </div>
                      </div>
                      <button
                        onClick={(e) => handleDelete(e, session.chat_id)}
                        className={`opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded ${
                          deleteConfirm === session.chat_id
                            ? 'text-red-400 hover:text-red-300'
                            : 'text-gray-400 hover:text-red-400'
                        }`}
                        title={deleteConfirm === session.chat_id ? 'Click again to confirm' : 'Delete chat'}
                      >
                        {deleteConfirm === session.chat_id ? '⚠️' : '🗑️'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
    
          <div className="mt-4 pt-4 border-t border-gray-700">
            <p className="text-xs text-gray-500 text-center">
              {chatSessions.length} {chatSessions.length === 1 ? 'conversation' : 'conversations'}
            </p>
          </div>
        </div>
      );

}