import axios, { AxiosError } from 'axios';
import type {AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios';
import { TOKEN_STORAGE_KEYS } from '../config/auth0-config';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

const apiClient: AxiosInstance = axios.create({
    baseURL: API_BASE_URL,
    timeout: 30000,
    headers: {
        'Content-Type': 'application/json'
    },
});

/**
 * REQUEST INTERCEPTOR
 * 
 * Runs before EVERY request sent through this axios instance.
 * Adds the JWT token to the Authorization header.
 */
apiClient.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
        const token = sessionStorage.getItem(TOKEN_STORAGE_KEYS.ACCESS_TOKEN);
        
        if (token){
            config.headers.Authorization = `Bearer ${token}`;

            console.log('[Axios Interceptor] Added token to request:', {
                url: config.url,
                method: config.method,
                hasToken: true,
                tokenPreview: `${token.substring(0, 20)}...`,
              });
            } 
        else {
              console.warn('[Axios Interceptor] No token found in sessionStorage');
        }
            
        return config;
    },
    (error: AxiosError) => {
        console.error('[Axios Interceptor] Request error: ', error)
        return Promise.reject(error);
    }
)

/**
 * RESPONSE INTERCEPTOR
 * 
 * Runs after EVERY response received (or error).
 * Handles authentication errors globally.
*/

apiClient.interceptors.response.use(
    (response: AxiosResponse) => {
        return response;
    },
    async (error: AxiosError) => {
        const originalRequest = error.config;
        /**
         * Handle 401 Unauthorized
         * This means the token is invalid, expired, or missing
         */
        if (error.response?.status === 401) {
            console.error('[Axios Interceptor] 401 Unauthorized - Token invalid or expired');
            
            // Clear stored tokens
            sessionStorage.removeItem(TOKEN_STORAGE_KEYS.ACCESS_TOKEN);
            sessionStorage.removeItem(TOKEN_STORAGE_KEYS.ID_TOKEN);
            sessionStorage.removeItem(TOKEN_STORAGE_KEYS.EXPIRES_AT);
            sessionStorage.removeItem(TOKEN_STORAGE_KEYS.USER);
            
            // TODO: Implement token refresh logic here
            // For now, we'll let the Auth0Provider handle re-authentication
            
            // Optionally, emit a custom event to trigger re-login
            window.dispatchEvent(new CustomEvent('auth:tokenExpired'));
            
            return Promise.reject(error);
        }
        
        /**
         * Handle 403 Forbidden
         * User is authenticated but doesn't have permission for this resource
         */
        if (error.response?.status === 403) {
            console.error('[Axios Interceptor] 403 Forbidden - Insufficient permissions');
            // You could redirect to an "Access Denied" page here
        }
        
        /**
         * Handle network errors
         * No response means server is unreachable
         */
        if (!error.response) {
            console.error('[Axios Interceptor] Network error - Server unreachable');
        }
        
        // Pass error through to calling code
        return Promise.reject(error);
    }
);

export default apiClient;

export function isTokenExpired(): boolean {
    const expiresAt = sessionStorage.getItem(TOKEN_STORAGE_KEYS.EXPIRES_AT);

    if(!expiresAt) {
        return true;
    }

    const expirationTime = parseInt(expiresAt, 10);
    const currentTime = Date.now();

    return currentTime >= (expirationTime - 60000);
}

export function setAuthToken(accessToken: string, expiresIn: number): void {
    const expiresAt = Date.now() + (expiresIn * 1000);

    sessionStorage.setItem(TOKEN_STORAGE_KEYS.ACCESS_TOKEN, accessToken);
    sessionStorage.setItem(TOKEN_STORAGE_KEYS.EXPIRES_AT, expiresAt.toString());

    console.log('[Auth] Token stored in sessionStorage', {
        expiresIn: `${expiresIn} seconds`,
        expiresAt: new Date(expiresAt).toISOString(),
      });

}

export function clearAuthTokens(): void {
    sessionStorage.removeItem(TOKEN_STORAGE_KEYS.ACCESS_TOKEN);
    sessionStorage.removeItem(TOKEN_STORAGE_KEYS.ID_TOKEN);
    sessionStorage.removeItem(TOKEN_STORAGE_KEYS.EXPIRES_AT);
    sessionStorage.removeItem(TOKEN_STORAGE_KEYS.USER);
    
    console.log('[Auth] All tokens cleared from sessionStorage');
}