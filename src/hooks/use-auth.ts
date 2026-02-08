import { useState, useEffect } from 'react';
import { blink } from '@/lib/blink';
import type { BlinkUser } from '@blinkdotnew/sdk';

export interface AuthState {
  user: BlinkUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

/**
 * Hook to manage authentication state using Blink SDK
 */
export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  });

  useEffect(() => {
    // Subscribe to auth state changes
    const unsubscribe = blink.auth.onAuthStateChanged((authState) => {
      setState({
        user: authState.user,
        isLoading: authState.isLoading,
        isAuthenticated: authState.isAuthenticated,
      });
    });

    return () => unsubscribe();
  }, []);

  const login = (redirectUrl?: string) => blink.auth.login(redirectUrl);
  const logout = () => blink.auth.signOut();

  return {
    ...state,
    login,
    logout,
  };
}
