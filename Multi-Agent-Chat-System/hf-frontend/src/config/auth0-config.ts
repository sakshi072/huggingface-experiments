export interface Auth0Config {
    domain: string;
    clientId: string;
    audience: string;
    redirectUri: string;
    scope: string;
    useRefreshTokens: boolean;
    cacheLocation: 'localstorage' | 'memory'
}

function validatEnvVars(): void {
    const required = {
        VITE_AUTH0_DOMAIN: import.meta.env.VITE_AUTH0_DOMAIN,
        VITE_AUTH0_CLIENT_ID: import.meta.env.VITE_AUTH0_CLIENT_ID,
        VITE_AUTH0_AUDIENCE: import.meta.env.VITE_AUTH0_AUDIENCE,
        VITE_AUTH0_REDIRECT_URI: import.meta.env.VITE_AUTH0_REDIRECT_URI,
    };

    const missing = Object.entries(required)
        .filter(([_, value]) => !value)
        ?.map(([key]) => key);
    
    if (missing.length > 0){
        throw new Error(
            `Missing required Auth0 environment variables: ${missing.join(', ')}\n` +
            'Please check your .env file.'
        );
    }
}

validatEnvVars();

/**
 * Auth0 Configuration Object
 * 
 * @property domain - Your Auth0 tenant domain (e.g., 'tenant.auth0.com')
 * @property clientId - Application Client ID from Auth0 dashboard
 * @property audience - API identifier (tells Auth0 which API to grant access to)
 * @property redirectUri - Where Auth0 redirects after login
 * @property scope - Permissions requested (openid, profile, email are standard)
 * @property useRefreshTokens - Enable refresh token rotation for security
 * @property cacheLocation - Where to store tokens ('memory' is more secure)
 */
 export const auth0Config: Auth0Config = {
    domain: import.meta.env.VITE_AUTH0_DOMAIN,
    clientId: import.meta.env.VITE_AUTH0_CLIENT_ID,
    audience: import.meta.env.VITE_AUTH0_AUDIENCE,
    redirectUri: import.meta.env.VITE_AUTH0_REDIRECT_URI,
    
    /**
     * Scopes define what information/permissions you're requesting:
     * - openid: Required for OIDC, gets you an ID token
     * - profile: User's profile info (name, picture, etc.)
     * - email: User's email address
     * - offline_access: Enables refresh tokens
     */
    scope: 'openid profile email offline_access',
    
    /**
     * Refresh tokens allow getting new access tokens without re-login
     * Recommended for better UX (user stays logged in longer)
     */
    useRefreshTokens: true,
    
    /**
     * Token storage location:
     * - 'memory': Most secure, tokens lost on page refresh
     * - 'localstorage': Persists tokens, vulnerable to XSS
     * 
     * We use 'memory' and handle session persistence via sessionStorage separately
     */
    cacheLocation: 'localstorage',
  };

  export const auth0ProviderConfig = {
    domain: auth0Config.domain,
    clientId: auth0Config.clientId,
    authorizationParams: {
        redirect_uri: auth0Config.redirectUri,
        audience: auth0Config.audience,
        scope: auth0Config.scope,
    },
    useRefreshTokens: auth0Config.useRefreshTokens,
    cacheLocation: auth0Config.cacheLocation,
  };

  /**
 * Helper to get the logout URL
 * Redirects user to Auth0's logout endpoint, then back to your app
 */

export function getLogoutUrl(): string {
    const returnTo = encodeURIComponent(window.location.origin);
    return `https://${auth0Config.domain}/v2/logout?client_id=${auth0Config.clientId}&returnTo=${returnTo}`;
}

/**
 * Token storage keys
 * Used for sessionStorage persistence (fallback mechanism)
 */

export const TOKEN_STORAGE_KEYS = {
    ACCESS_TOKEN: 'auth0_access_token',
    ID_TOKEN: 'auth0_id_token',
    EXPIRES_AT: 'auth0_expires_at',
    USER: 'auth0_user',
} as const;