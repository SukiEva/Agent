/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AGENT_SERVER_URL?: string;
  readonly VITE_AGENT_USER_ID?: string;
  readonly VITE_AGENT_TENANT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";

  const component: DefineComponent<object, object, unknown>;
  export default component;
}
