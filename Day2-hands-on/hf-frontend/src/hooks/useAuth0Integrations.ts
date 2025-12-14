import { useEffect, useCallback } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import { setAuthToken, clearAuthTokens } from '../api/axios-instance';
import { TOKEN_STORAGE_KEYS } from '../config/auth0-config';
import { useAuthStore } from '../stores/authStore';

export function useAuth0Integration() {
    const {
        isAuthenticated,
        isLoading,
        user,
        getAccessTokenSilently,
        logout: auth0Logout,
    } = useAuth0();

    const {
        setUserId,
        setIsAuthenticated,
        setIsLoaded,
        resetAuth
    } = useAuthStore();

    /**
     * Fetch and store the access token
     * 
     * WHEN THIS RUNS:
     * - After successful login
     * - On app mount if user is authenticated
     * - Before token expiration (via Auth0's internal refresh)
     * 
     */

    const storeAccessToken = useCallback(async () => {
        if(!isAuthenticated){
            return null
        }

        try {
            const token = await getAccessTokenSilently({
                authorizationParams:{
                    audience: import.meta.env.VITE_AUTH0_AUDIENCE,
                },
            });

            setAuthToken(token, 86400);

            console.log('[Auth0 Integration] Token stored successfully');
            return token;
        } catch(error){
            console.error('[Auth0 Integration] Error getting access token:', error)
            clearAuthTokens();
            return null;
        }
    }, [isAuthenticated, getAccessTokenSilently, resetAuth])

    /**
     * Store user information
     * 
     * Saves user profile data to sessionStorage
     * This is optional but useful for displaying user info without hitting Auth0 API
     */
    const storeUserInfo = useCallback(() => {
        if(user) {
            sessionStorage.setItem(TOKEN_STORAGE_KEYS.USER, JSON.stringify(user));
            console.log('[Auth0 Integration] User info stored:', {
                sub: user.sub,
                email: user.email,
                name: user.name
            });
        }
    }, [user])

    /**
     * Handle logout
     * 
     * WHAT IT DOES:
     * 1. Clear sessionStorage
     * 2. Reset Zustand auth store
     * 3. Call Auth0's logout (clears Auth0 session + redirects)
     */

    const handleLogout = useCallback(() => {
        console.log('[Auth0 Integration] Logging out...')

        clearAuthTokens();
        resetAuth();

        auth0Logout({
            logoutParams: {
                returnTo: window.location.origin
            }
        });
    }, [auth0Logout, resetAuth])

    /**
     * Effect: Initialize authentication on mount
     * 
     * Runs when Auth0 finishes loading
     * If user is authenticated, fetch and store token
     */
    useEffect(() => {
        const initAuth = async () => {
            console.log('[Auth0 Integration] Initializing...', {
                isLoading,
                isAuthenticated,
                hasUser: !!user
            });

            if(isLoading){
                setIsLoaded(false);
                return;
            }

            setIsLoaded(true);

            if(isAuthenticated && user){
                await storeAccessToken();
                storeUserInfo();

                setUserId(user.sub || null);
                setIsAuthenticated(true);
                console.log('[Auth0 Integration] User authenticated:', user.sub)
            } else {
                setIsAuthenticated(false);
                setUserId(null);
                console.log('[Auth0 Integration] User not authenticated');
            }
        };

        initAuth()
    }, [
        isLoading,
        isAuthenticated,
        user,
        storeAccessToken,
        storeUserInfo,
        setUserId,
        setIsAuthenticated,
        setIsLoaded
    ]);

    /**
     * Effect: Set up token refresh before expiration
     * 
     * Proactively refreshes token before it expires
     * This prevents 401 errors during active usage
     */
    useEffect(() => {
        if(!isAuthenticated) return;

        // Refresh token every 30 minutes
        const refreshInterval = setInterval(async () => {
            console.log('[Auth0 Integration] Proactive token refresh...')
            await storeAccessToken();
        }, 30*60*1000);

        return () => clearInterval(refreshInterval);
    }, [isAuthenticated, storeAccessToken]);

    /**
     * Effect: Listen for token expiration events
     * 
     * If axios interceptor detects 401, it fires 'auth:tokenExpired' event
     * We catch it here and try to refresh
     */
    useEffect(() => {
        const handleTokenExpired = async () => {
            console.warn('[Auth0 Integration] Token expired, attempting refresh...');
            const newToken = await storeAccessToken();

            if(!newToken){
                handleLogout();
            }
        };

        window.addEventListener('auth:tokenExpired', handleTokenExpired);
        return () => {
            window.removeEventListener('auth:tokenExpired', handleTokenExpired);
        };
    }, [storeAccessToken, handleLogout]);

    return {
        isAuthenticated,
        isLoading,
        user,
        logout: handleLogout,
        refreshToken: storeAccessToken,
    };
}