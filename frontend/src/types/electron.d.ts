/**
 * Electron preload bridge — methods exposed via contextBridge in the desktop shell.
 * All methods are optional: the web build runs without Electron, so callers must
 * always guard with `window.electronAPI?.method?.()`.
 */
interface ElectronAPI {
  /** Open a native directory picker, returns the chosen path or null if cancelled. */
  pickDirectory?: () => Promise<string | null>
  /** Alias used by some panels for output directory selection. */
  pickOutputDir?: () => Promise<string | null>
  /** Open a native video file picker, returns the chosen path or null if cancelled. */
  pickVideoFile?: () => Promise<string | null>
  /** Open the given path in the OS file manager / default application. */
  openPath?: (path: string) => Promise<void> | void
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

export {}
