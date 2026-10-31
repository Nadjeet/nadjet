/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  /** SIM number of the SMS gateway used by the public report page's offline fallback. */
  readonly VITE_SMS_GATEWAY_NUMBER?: string;
}
