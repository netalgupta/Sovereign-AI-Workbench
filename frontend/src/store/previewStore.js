import { create } from 'zustand'

/**
 * Global store for managing source file preview state across all components.
 */
export const usePreviewStore = create((set) => ({
  file: null,
  isOpen: false,
  /**
   * Opens preview modal for a given file node object or file path identifier string.
   * @param {Object|string} fileOrPath 
   */
  openPreview: (fileOrPath) => {
    if (!fileOrPath) return
    let fileObj = fileOrPath
    if (typeof fileOrPath === 'string') {
      const name = fileOrPath.split(/[/\\]/).pop()
      fileObj = {
        id: fileOrPath,
        name: name,
        filename: name,
        relativePath: fileOrPath,
        relPath: fileOrPath,
      }
    }
    set({ file: fileObj, isOpen: true })
  },
  /**
   * Closes the global preview modal.
   */
  closePreview: () => set({ isOpen: false, file: null }),
}))
