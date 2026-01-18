import React from 'react';
import { Auth0Provider, useAuth0 } from '@auth0/auth0-react';
import { auth0ProviderConfig } from './config/auth0-config';
import { useAuth0Integration } from './hooks/useAuth0Integrations';
import { useChat } from './hooks/useChat';
import { ChatContainer } from './components/Chat/ChatContainer';
import { Sidebar } from './components/Sidebar/Sidebar';
import { useUIStore } from './stores';

// Get your Clerk Publishable Key from environment variables
/**
 * Loading Component
 * Shown while Auth0 is initializing
 */
 const LoadingScreen: React.FC = () => (
  <div className="flex items-center justify-center h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
    <div className="text-center">
      <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-600 mx-auto mb-4"></div>
      <p className="text-xl font-semibold text-gray-700">Loading HUGG Chat...</p>
      <p className="text-sm text-gray-500 mt-2">Initializing secure connection</p>
    </div>
  </div>
);

/**
 * Login Screen Component
 * Shown when user is not authenticated
 */

const LoginScreen: React.FC = () => {
  const { loginWithRedirect } = useAuth0();

  const handleLogin = async () => {
    try{
      /**
       * loginWithRedirect() flow:
       * 
       * 1. Generate PKCE code_verifier (random string)
       * 2. Hash code_verifier → code_challenge
       * 3. Redirect to Auth0 with code_challenge
       * 4. User logs in at Auth0
       * 5. Auth0 redirects back with authorization_code
       * 6. Exchange code for tokens (Auth0 validates code_verifier)
       * 7. Store tokens and user is authenticated
       * 
       * PKCE Security:
       * Even if authorization_code is intercepted, attacker can't
       * exchange it without the original code_verifier (only in memory)
       */
      await loginWithRedirect({
        authorizationParams: {
          audience: auth0ProviderConfig.authorizationParams.audience,
          scope: auth0ProviderConfig.authorizationParams.scope,
        },
        appState: {
          returnTo: window.location.pathname,
        }
      });
    } catch (error) {
      console.error('Login error: ', error);
    }
  };

  return (
    <div className="flex items-center justify-center h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="text-center p-8 bg-white rounded-2xl shadow-xl max-w-md">
        <div className="text-6xl mb-4">🤗</div>
        <h1 className="text-4xl font-bold mb-2 text-gray-800">HUGG Chat</h1>
        <p className="text-gray-600 mb-6">
          Sign in to start chatting with your AI assistant
        </p>
        
        <button
          onClick={handleLogin}
          className="px-8 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-semibold shadow-lg hover:shadow-xl w-full"
        >
          Sign In with Auth0
        </button>
        
        <div className="mt-6 text-xs text-gray-400 space-y-1">
          <p>🔒 Secure OpenID Connect authentication</p>
          <p>🛡️ Protected with PKCE</p>
          <p>✨ Powered by Auth0</p>
        </div>
      </div>
    </div>
  );
};

/**
 * User Profile Display Component
 * Shows current user's info with logout button
 * 
 * Export this component so Sidebar can use it
 */

export const UserProfile: React.FC = () => {
  const { user } = useAuth0();
  const { logout } = useAuth0Integration();

  if (!user) return null;

  return (
    <div className="mt-3 pt-3 border-t border-gray-700 flex items-center justify-between gap-3">
      <div className="flex items-center gap-3 min-w-0">
        {/* User Avatar */}
        {user.picture ? (
          <img
            src={user.picture}
            alt={user.name || 'User'}
            className="w-8 h-8 rounded-full"
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white font-semibold">
            {(user.name || user.email || 'U')[0].toUpperCase()}
          </div>
        )}
        
        {/* User Info */}
        <div className="flex flex-col min-w-0">
          <span className="text-xs font-medium truncate">
            {user.name || user.email || 'User'}
          </span>
          <span className="text-[10px] text-gray-500 truncate">
            {user.email}
          </span>
        </div>
      </div>
      
      {/* Logout Button */}
      <button
        onClick={logout}
        className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
        title="Logout"
      >
        <svg
          className="w-5 h-5 text-gray-400 hover:text-white"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
          />
        </svg>
      </button>
    </div>
  );
};

/**
 * Authenticated App Component
 * The main app interface shown after login
 */

const AuthenticatedApp: React.FC = () => {
  // Initialize Auth0 integration (handles token storage)
  useAuth0Integration();

  // Initialize chat logic
  const chatLogic = useChat();
  const { toggleSidebar } = useUIStore();

  if (!chatLogic.isAuthenticated){
    return <LoadingScreen/>;
  }

  return (
    <div className="flex h-screen bg-white relative">
      {/* Mobile hamburger button */}
      <button
        className="absolute top-4 left-4 z-30 p-2 bg-gray-900 text-white rounded-md lg:hidden"
        onClick={toggleSidebar}
        aria-label="Toggle sidebar"
      >
        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      
      {/* Sidebar with chat sessions */}
      <Sidebar />
      
      {/* Main chat area */}
      <div className="flex-grow">
        <ChatContainer />
      </div>
    </div>
  );
};

/**
 * Main App Component
 * Wraps everything in Auth0Provider
 */

const App: React.FC = () => {
  const { isLoading, isAuthenticated, error } = useAuth0();

  /**
   * Handle Auth0 errors
   * Could be network issues, configuration errors, etc.
   */
   if (error) {
    return (
      <div className="flex items-center justify-center h-screen bg-red-50">
        <div className="text-center p-8 bg-white rounded-2xl shadow-xl max-w-md">
          <div className="text-4xl mb-4">⚠️</div>
          <p className="text-red-600 font-semibold mb-2">Authentication Error</p>
          <p className="text-gray-600 text-sm mb-4">{error.message}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  /**
   * Show loading while Auth0 initializes
   * This includes checking for existing session
   */

  if(isLoading) {
    return <LoadingScreen />;
  }

  /**
   * Show appropriate screen based on auth state
   */

  if (!isAuthenticated){
    return <LoginScreen/>;
  }

  return <AuthenticatedApp/>;

};

/**
 * Root App Component with Auth0Provider
 * This is the entry point that gets rendered in main.tsx
 */

const AppWithAuth0: React.FC = () => {
  return(
    <Auth0Provider
      {...auth0ProviderConfig}
      onRedirectCallback={(appState) => {
        // After login redirect, navigate to where user was trying to go
        window.history.replaceState(
          {},
          document.title,
          appState?.returnTo || window.location.pathname
        );
      }}
      >
        <App />
      </Auth0Provider>
  );
};

export default AppWithAuth0;