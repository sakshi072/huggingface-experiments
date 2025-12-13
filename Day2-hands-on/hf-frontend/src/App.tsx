import React from 'react';
import { ClerkProvider, SignedIn, SignedOut, SignInButton, UserButton, useUser } from '@clerk/clerk-react';
import { useChat } from './hooks/useChat';
import { ChatContainer } from './components/Chat/ChatContainer';
import { Sidebar } from './components/Sidebar/Sidebar';
import { useUIStore } from './stores';

// Get your Clerk Publishable Key from environment variables
const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

const AuthenticatedApp: React.FC = () => {
  const chatLogic = useChat();
  const { user } = useUser();
  const { toggleSidebar } = useUIStore();

  if (!chatLogic.isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading your chats...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-white relative">
      {/* Global mobile hamburger */}
      <button className="asolute top-4 left-4 z-30 p-2 bg-gray-900 text-white rounded-md lg:hidden"
        onClick={toggleSidebar}>

      </button>
      <Sidebar />
      
      <div className="flex-grow"> 
        <ChatContainer  />
      </div>
    </div>
  );
};

const App: React.FC = () => {
  if (!CLERK_PUBLISHABLE_KEY) {
    return (
      <div className="flex items-center justify-center h-screen bg-red-50">
        <div className="text-center p-8 bg-white rounded-2xl shadow-xl max-w-md">
          <p className="text-red-600 font-semibold mb-2">⚠️ Configuration Error</p>
          <p className="text-gray-600 text-sm">Missing Clerk Publishable Key</p>
          <p className="text-gray-500 text-xs mt-2">
            Please add VITE_CLERK_PUBLISHABLE_KEY to your .env file
          </p>
        </div>
      </div>
    );
  }

  return (
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>
      <SignedOut>
        <div className="flex items-center justify-center h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
          <div className="text-center p-8 bg-white rounded-2xl shadow-xl max-w-md">
            <div className="text-6xl mb-4">🤗</div>
            <h1 className="text-4xl font-bold mb-2 text-gray-800">HUGG Chat</h1>
            <p className="text-gray-600 mb-6">
              Sign in to start chatting with your AI assistant
            </p>
            <SignInButton mode="modal">
              <button className="px-8 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-semibold shadow-lg hover:shadow-xl">
                Sign In
              </button>
            </SignInButton>
            <p className="text-xs text-gray-400 mt-4">
              Secure authentication powered by Clerk
            </p>
          </div>
        </div>
      </SignedOut>

      <SignedIn>
        <AuthenticatedApp />
      </SignedIn>
    </ClerkProvider>
  );
};

export default App;