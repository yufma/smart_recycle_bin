/// <reference types="vite/client" />
export {};
declare global {
  interface Window {
    inloopPublicDemo?: boolean;
    inloopDemoStatus?: string;
    inloopDemoApi?: <T>(path: string, options?: RequestInit) => Promise<T>;
  }
}
