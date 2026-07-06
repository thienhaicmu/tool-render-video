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
  /** Reveal a file in the OS file manager, selecting/highlighting it. Prefer
   *  this over openPath(dir) for "open folder" so the exact file is picked out
   *  even in a busy folder, and it handles drive-root paths correctly. */
  showItemInFolder?: (path: string) => Promise<string | void> | string | void
  /** Open a native file picker for cookies.txt, returns the chosen path or null. */
  pickCookiesFile?: () => Promise<string | null>
  /** Check whether a path exists on disk. Returns null on IPC failure
   *  (caller should treat that as "unknown — skip the check"). */
  pathExists?: (path: string) => Promise<boolean | null>
  /** Show an OS-level notification (Win11 Action Center / macOS Notification
   *  Center). Returns ok=false if the platform doesn't support notifications
   *  or IPC failed. The web build is a no-op (method is undefined). */
  notify?: (opts: {
    title: string
    body?: string
    jobId?: string
    kind?: 'render' | 'download'
  }) => Promise<{ ok: boolean; error?: string }>
  /** Subscribe to "user clicked an OS notification" events. Returns an
   *  unsubscribe function. Useful for navigating to the relevant screen
   *  (e.g. Results for the jobId carried in the original notify() call). */
  onNotificationClicked?: (
    handler: (payload: { jobId: string | null; kind: string | null }) => void,
  ) => () => void
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

export {}
