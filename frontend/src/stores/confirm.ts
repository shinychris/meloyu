import { create } from 'zustand'

interface ConfirmOptions {
  title: string
  description?: string
  confirmText?: string
  danger?: boolean
}

interface ConfirmState {
  visible: boolean
  options: ConfirmOptions | null
  resolver: ((ok: boolean) => void) | null
  /** 弹出确认框，返回 Promise<boolean>；敏感操作（永久删除等）必须走这里 */
  confirm: (options: ConfirmOptions) => Promise<boolean>
  resolve: (ok: boolean) => void
}

export const useConfirmStore = create<ConfirmState>((set, get) => ({
  visible: false,
  options: null,
  resolver: null,
  confirm(options) {
    return new Promise<boolean>((resolve) => {
      set({ visible: true, options, resolver: resolve })
    })
  },
  resolve(ok) {
    get().resolver?.(ok)
    set({ visible: false, options: null, resolver: null })
  },
}))

/** 非组件场景的确认弹窗 */
export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  return useConfirmStore.getState().confirm(options)
}
