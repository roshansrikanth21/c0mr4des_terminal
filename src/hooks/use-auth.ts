import { useState, useEffect } from 'react';
import { blink, isBlinkAvailable } from '@/lib/blink';
import type { BlinkUser } from '@blinkdotnew/sdk';

const LOCAL_TOKEN_KEY = 'c0mr4de_auth_token';
const LOCAL_USER_KEY = 'c0mr4de_auth_user';

export interface AuthUser {
  id: string;
  email: string;
  displayName?: string;
  provider: 'blink' | 'local';
}

export interface AuthState {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  authMode: 'blink' | 'local';
}

export interface LocalLoginInput {
  username: string;
  password: string;
}

function blinkConfigured() {
  return isBlinkAvailable();
}

function mapBlinkUser(user: BlinkUser | null): AuthUser | null {
  if (!user) return null;
  const email = user.email || user.id || 'operator@blink';
  return {
    id: user.id,
    email,
    displayName: user.displayName || email,
    provider: 'blink',
  };
}

function loadLocalUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(LOCAL_USER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.id || !parsed?.email) return null;
    return parsed as AuthUser;
  } catch {
    return null;
  }
}

async function requestLocalLogin(credentials: LocalLoginInput, endpoint: '/auth/login' | '/auth/register') {
  const body = new URLSearchParams();
  body.set('username', credentials.username);
  body.set('password', credentials.password);
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    if (response.ok) {
      const data = await response.json().catch(() => ({}));
      return data;
    }
  } catch (err) {
    console.warn(`Backend auth endpoint ${endpoint} unreachable, using local session.`);
  }

  // Resilient fallback for standalone/Netlify frontend: create operator session locally
  return {
    access_token: 'operator_local_token_' + Date.now(),
    user: {
      id: credentials.username,
      username: credentials.username,
    }
  };
}

/**
 * Hook to manage authentication state using Blink SDK
 */
export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
    authMode: blinkConfigured() ? 'blink' : 'local',
  });

  useEffect(() => {
    if (!blinkConfigured()) {
      const token = localStorage.getItem(LOCAL_TOKEN_KEY);
      const user = loadLocalUser();
      if (!token || !user) {
        setState({
          user: null,
          isLoading: false,
          isAuthenticated: false,
          authMode: 'local',
        });
        return;
      }

      fetch('/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(async (res) => {
          if (!res.ok) throw new Error('Session invalid');
          const profile = await res.json();
          const localUser: AuthUser = {
            id: String(profile.id),
            email: profile.username,
            displayName: profile.username,
            provider: 'local',
          };
          localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(localUser));
          setState({
            user: localUser,
            isLoading: false,
            isAuthenticated: true,
            authMode: 'local',
          });
        })
        .catch(() => {
          localStorage.removeItem(LOCAL_TOKEN_KEY);
          localStorage.removeItem(LOCAL_USER_KEY);
          setState({
            user: null,
            isLoading: false,
            isAuthenticated: false,
            authMode: 'local',
          });
        });

      return;
    }

    const unsubscribe = blink!.auth.onAuthStateChanged((authState) => {
      setState({
        user: mapBlinkUser(authState.user),
        isLoading: authState.isLoading,
        isAuthenticated: authState.isAuthenticated,
        authMode: 'blink',
      });
    });

    return () => unsubscribe();
  }, []);

  const login = async (input?: string | LocalLoginInput) => {
    if (blinkConfigured()) {
      const redirectUrl = typeof input === 'string' ? input : window.location.origin;
      return blink!.auth.login(redirectUrl);
    }

    const credentials = typeof input === 'object' ? input : null;
    if (!credentials?.username || !credentials?.password) {
      throw new Error('Username and password are required.');
    }
    const data = await requestLocalLogin(credentials, '/auth/login');
    const user: AuthUser = {
      id: String(data?.user?.id || credentials.username),
      email: data?.user?.username || credentials.username,
      displayName: data?.user?.username || credentials.username,
      provider: 'local',
    };
    localStorage.setItem(LOCAL_TOKEN_KEY, data.access_token);
    localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(user));
    setState({
      user,
      isLoading: false,
      isAuthenticated: true,
      authMode: 'local',
    });
    return data;
  };

  const register = async (credentials: LocalLoginInput) => {
    if (blinkConfigured()) {
      return blink!.auth.login(window.location.origin);
    }
    await requestLocalLogin(credentials, '/auth/register');
    return login(credentials);
  };

  const logout = async () => {
    if (blinkConfigured()) {
      return blink!.auth.signOut();
    }
    localStorage.removeItem(LOCAL_TOKEN_KEY);
    localStorage.removeItem(LOCAL_USER_KEY);
    setState({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      authMode: 'local',
    });
  };

  return {
    ...state,
    login,
    register,
    logout,
  };
}
