import { createClient } from '@blinkdotnew/sdk';

/**
 * Blink SDK Client initialization
 * 
 * projectId and publishableKey are automatically injected into the environment
 * by the Blink platform. We use these to initialize the client with managed auth.
 */
const blinkProjectId = import.meta.env.VITE_BLINK_PROJECT_ID;
const blinkPublishableKey = import.meta.env.VITE_BLINK_PUBLISHABLE_KEY;
const blinkExplicitlyEnabled = String(import.meta.env.VITE_ENABLE_BLINK_AUTH || '').toLowerCase() === 'true';

export const blink = blinkExplicitlyEnabled && blinkProjectId && blinkPublishableKey
  ? createClient({
      projectId: blinkProjectId,
      publishableKey: blinkPublishableKey,
      auth: { mode: 'managed' },
    })
  : null;

export function isBlinkAvailable() {
  return Boolean(blink);
}
