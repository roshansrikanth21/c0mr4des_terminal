import { createClient } from '@blinkdotnew/sdk';

/**
 * Blink SDK Client initialization
 * 
 * projectId and publishableKey are automatically injected into the environment
 * by the Blink platform. We use these to initialize the client with managed auth.
 */
export const blink = createClient({
  projectId: import.meta.env.VITE_BLINK_PROJECT_ID,
  publishableKey: import.meta.env.VITE_BLINK_PUBLISHABLE_KEY,
  auth: { mode: 'managed' },
});
