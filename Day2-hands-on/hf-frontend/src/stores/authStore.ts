import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

interface AuthState {
    userId: string | null;
    isAuthenticated: boolean;
    isLoaded: boolean;
    hasInitialized: boolean;
    
    // Actions
    setUserId: (userId: string | null) => void;
    setIsAuthenticated: (auth: boolean) => void;
    setIsLoaded: (loaded: boolean) => void;
    setHasInitialized: (initialized: boolean) => void;
    
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
        
        // Actions
        setUserId: (userId) => set({ userId }),
        
        setIsAuthenticated: (auth) => set({ isAuthenticated: auth }),
        
        setIsLoaded: (loaded) => set({ isLoaded: loaded }),
        
        setHasInitialized: (initialized) => set({ hasInitialized: initialized }),
        
        // Reset
        resetAuth: () => set({
          userId: null,
          isAuthenticated: false,
          isLoaded: false,
          hasInitialized: false,
        }),
      }),
      { name: 'AuthStore' }
    )
  );