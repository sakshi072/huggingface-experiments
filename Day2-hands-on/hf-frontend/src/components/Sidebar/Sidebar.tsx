import React, {useState, useRef, useEffect, useCallback} from "react";
import { ConfirmationModal } from "../Modals/ConfirmationModal";
import { EditTitleModal } from "../Modals/EditTitleModal";
import { useChatStore, useUIStore } from "../../stores";
import { useChat } from "../../hooks/useChat";
import { HamburgerButton } from "../Buttons/HumburgerButton";
import { UserProfile } from "../../App";

const SESSIONS_PER_PAGE = 20;

export const Sidebar: React.FC = () => {
    const { chatSessions, currentChatId, hasMoreSessions } = useChatStore();
    const { isSidebarOpen, toggleSidebar, setSidebarOpen } = useUIStore();
    const { startNewChat, switchToChat, deleteChat, updateChatTitle, loadMoreSessions } = useChat();

    const [chatToDelete, setChatToDelete] = useState<{ id:string; title:string } | null>(null);
    const [chatToEdit, setChatToEdit] = useState<{ id:string; title:string } | null>(null);
    const [isLoadingMoreSessions, setIsLoadingMoreSessions] = useState(false);
    // const [isSideBarOpen, setIsSideBarOpen] = useState(false);

    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const isLoadingMoreRef = useRef(false);

    const formatDate = (dateString:string) => {
        const date = new Date(dateString);
        const now = new Date();

        const nowDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const dateDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());

        const diffMs = nowDay.getTime() - dateDay.getTime();
        const diffDays = Math.floor(diffMs/(1000 * 60 * 60 * 24));

        if(diffDays === 0) return 'Today';
        if(diffDays === 1) return 'Yesterday';
        if(diffDays < 7) return `${diffDays} days ago`;
        return date.toLocaleDateString();
    };

    const handleDeleteClick = (e: React.MouseEvent, chatId: string, chatTitle:string) => {
        e.stopPropagation();
        setChatToDelete({id:chatId, title:chatTitle})
    };

    const handleEditClick = (e: React.MouseEvent, chatId: string, chatTitle:string) => {
        e.stopPropagation();
        setChatToEdit({id:chatId, title:chatTitle})
    }

    const handleConfirmDelete = () => {
        if(chatToDelete){
            deleteChat(chatToDelete.id)
            setChatToDelete(null);
        }
    };

    const handleSaveTitle = (newTitle:string) => {
        if(chatToEdit){
            updateChatTitle(chatToEdit.id, newTitle);
            setChatToEdit(null);
        }
    }

    // Fixed scroll handler
    const handleScroll = useCallback(() => {
        if(!scrollContainerRef.current || !loadMoreSessions) return;

        if(isLoadingMoreRef.current || !hasMoreSessions) return;

        const container = scrollContainerRef.current;
        const { scrollTop, scrollHeight, clientHeight } = container;

        // Load more when scrolled near the bottom (within 100px)
        if (scrollHeight - scrollTop - clientHeight < 100) {
            isLoadingMoreRef.current = true;
            setIsLoadingMoreSessions(true);

            loadMoreSessions().finally(() => {
                setIsLoadingMoreSessions(false);
                setTimeout(()=>{
                    isLoadingMoreRef.current = false;
                }, 500)
            });
        }
    }, [loadMoreSessions, hasMoreSessions]);

    useEffect(() => {
        const container = scrollContainerRef.current;
        if (!container) return; 

        container.addEventListener('scroll', handleScroll, { passive: true });

        return () => {
            container.removeEventListener('scroll', handleScroll);
        }
    }, [handleScroll])

    const collapsedClass = isSidebarOpen ? 'lg:w-80' : 'lg:w-16';
    const mobileCollapseClass = isSidebarOpen ? 'translate-x-0' : '-translate-x-full';
    const contentVisibleClass = isSidebarOpen ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-2 pointer-events-none';
    // Compute classes based on isSidebarOpen
    const bottomSectionVisibleClass = isSidebarOpen ? 'opacity-100 translate-x-0' : 'opacity-0 pointer-events-none';
    const bottomTextHiddenClass = !isSidebarOpen ? 'lg:hidden' : '';
    const bottomRowJustifyClass = isSidebarOpen ? 'justify-between px-2' : 'justify-center';


    return (
        <>  
            <div className={`
                    w-full ${collapsedClass} bg-gray-900 text-white flex flex-col h-full p-4 border-r border-gray-700 z-20
                    transition-all duration-300 ease-in-out
                    
                    fixed inset-y-0 left-0 lg:static ${mobileCollapseClass} 
                    lg:flex-shrink-0 lg:h-full lg:translate-x-0
                `}>
            <div className="flex items-center justify-between mb-6">
            <h2 className={`text-xl font-bold whitespace-nowrap ${!isSidebarOpen && 'lg:hidden'}`}>
                        🤗 HUGG Chat
                    </h2>
                <HamburgerButton 
                    isOpen={isSidebarOpen} 
                    setIsOpen={toggleSidebar} 
                />
            </div>
            <button 
                onClick={startNewChat} 
                className={`w-full py-2 px-4 mb-4 border border-gray-600 rounded-lg hover:bg-gray-700 transition-colors flex items-center justify-center gap-2 ${!isSidebarOpen && 'lg:py-4 lg:w-full'}`}
                >
                <span>➕</span>
                <span className={`${!isSidebarOpen && 'lg:hidden'}`}>New Chat</span>
            </button>
        
            <div
                ref={scrollContainerRef} 
                className={`flex-grow overflow-y-auto scrollbar-thin scrollbar-thumb-gray-600 transition-all duration-300 ${contentVisibleClass}`}
                style={{
                    // Ensure scroll is visible
                    overflowY: 'auto',
                    maxHeight: '100%'
                }}
            >
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
                        onClick={() => switchToChat(session.chat_id)}
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
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            {/* Edit Button */}
                            <button
                                onClick={(e) => handleEditClick(e, session.chat_id, session.title)}
                                className="p-1 rounded text-gray-400 hover:text-blue-400 hover:bg-gray-700"
                                title="Rename chat"
                            >
                                <svg 
                                    className="w-4 h-4" 
                                    fill="none" 
                                    viewBox="0 0 24 24" 
                                    stroke="currentColor"
                                >
                                    <path 
                                        strokeLinecap="round" 
                                        strokeLinejoin="round" 
                                        strokeWidth={2} 
                                        d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" 
                                    />
                                </svg>
                            </button>
                            <button
                                onClick={(e) => handleDeleteClick(e, session.chat_id, session.title)}
                                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded text-gray-400 hover:text-red-400 hover:bg-gray-700"
                                title='Delete chat'
                            >
                                <svg 
                                    className="w-5 h-5" 
                                    fill="none" 
                                    viewBox="0 0 24 24" 
                                    stroke="currentColor"
                                >
                                    <path 
                                        strokeLinecap="round" 
                                        strokeLinejoin="round" 
                                        strokeWidth={2} 
                                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" 
                                    />
                                </svg>
                            </button>
                        </div>
                        </div>
                    </div>
                    ))}

                    {/* Loading indicator */}
                    {isLoadingMoreSessions && (
                        <div className="text-center py-4 text-blue-400">
                            <div className="flex items-center justify-center gap-2">
                                <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                <span className="text-sm">Loading more...</span>
                            </div>
                        </div>
                    )}

                    {/* End of list indicator */}
                    {!hasMoreSessions && chatSessions.length > SESSIONS_PER_PAGE && (
                        <div className="text-center py-4 text-gray-500">
                            <span className="text-xs">• All chats loaded •</span>
                        </div>
                    )}
                </div>
                )}
            </div>
        
            <div className={`mt-4 pt-4 border-t border-gray-700 ${bottomSectionVisibleClass}`}>
                <p className="text-xs text-gray-500 text-center">
                {chatSessions.length} {chatSessions.length === 1 ? 'chat' : 'chats'}
                {hasMoreSessions && ' (scroll for more)'}
                </p>
            </div>
                {/* Use the UserProfile component from App.tsx */}
                <UserProfile />
            </div>

            {isSidebarOpen && (
                <div
                    className="fixed inset-0 bg-black opacity-50 z-10 lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Confirmation Modal */}
            <ConfirmationModal
                isOpen={chatToDelete !== null}
                title="Delete Chat"
                message={`Are you sure you want to delete "${chatToDelete?.title || 'this chat'}"? This action cannot be undone.`}
                confirmText="Delete"
                cancelText="Cancel"
                onConfirm={handleConfirmDelete}
                onCancel={() => setChatToDelete(null)}
                isDestructive={true}
            />

            <EditTitleModal
                isOpen={chatToEdit !== null}
                currentTitle={chatToEdit?.title || ''}
                onSave={handleSaveTitle}
                onCancel={() => setChatToEdit(null)}
            />
                    
        </>
    );

}