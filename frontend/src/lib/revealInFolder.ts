/**
 * revealInFolder — open the OS file manager and SELECT the given file.
 *
 * Prefers Electron `shell.showItemInFolder`, which highlights the exact file
 * (so a freshly rendered clip isn't lost among other files in a busy folder)
 * and handles drive-root paths correctly. Falls back to opening the containing
 * folder via `openPath` when the desktop build predates showItemInFolder.
 *
 * The web build (no electronAPI) is a silent no-op.
 */
export function revealInFolder(filePath: string): void {
  const p = (filePath || '').trim()
  if (!p) return
  const api = window.electronAPI
  if (api?.showItemInFolder) {
    void api.showItemInFolder(p)
    return
  }
  // Fallback: strip the filename → open the containing folder. Guarded against
  // the drive-root case ("D:\clip.mp4" would otherwise become "D:").
  const sep = p.includes('\\') ? '\\' : '/'
  const cut = p.lastIndexOf(sep)
  const dir = cut > 0 ? p.substring(0, cut) : p
  void api?.openPath?.(dir)
}
