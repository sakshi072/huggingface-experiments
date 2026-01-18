import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

interface AuthState {
    userId: string | null;
    isAuthenticated: boolean;
    isLoaded: boolean;
    hasInitialized: boolean;
    isTokenReady: boolean;

    // Actions
    setUserId: (userId: string | null) => void;
    setIsAuthenticated: (auth: boolean) => void;
    setIsLoaded: (loaded: boolean) => void;
    setHasInitialized: (initialized: boolean) => void;
    setIsTokenReady: (ready: boolean) => void;
    
    // Reset
    resetAuth: () => void;
  }

  export const useAuthStore = create<AuthState>()(
    devtools(
      (set) => ({
        // Initial state
        userId: null,
        isAuthenticated: false,
        isLoaded: false,
        hasInitialized: false,
        isTokenReady: false,
        
        // Actions
        setUserId: (userId) => set({ userId }),
        
        setIsAuthenticated: (auth) => set({ isAuthenticated: auth }),
        
        setIsLoaded: (loaded) => set({ isLoaded: loaded }),
        
        setHasInitialized: (initialized) => set({ hasInitialized: initialized }),
        
        setIsTokenReady: (ready) => set({ isTokenReady: ready }),
        // Reset
        resetAuth: () => set({
          userId: null,
          isAuthenticated: false,
          isLoaded: false,
          hasInitialized: false,
          isTokenReady: false,
        }),
      }),
      { name: 'AuthStore' }
    )
  );