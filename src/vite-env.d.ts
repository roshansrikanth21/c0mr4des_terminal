/// <reference types="vite/client" />

interface ImportMetaEnv {
    readonly VITE_ENABLE_BLINK_AUTH?: string
    readonly VITE_BLINK_PROJECT_ID?: string
    readonly VITE_BLINK_PUBLISHABLE_KEY?: string
    // more env variables...
}

interface ImportMeta {
    readonly env: ImportMetaEnv
}
