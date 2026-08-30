import { create } from 'zustand'

export interface ToastItem {
  id: number
  message: string
  kind: 'info' | 'warn' | 'bad'
}

interface ToastState {
  toasts: ToastItem[]
  push: (message: string, kind?: ToastItem['kind']) => void
  dismiss: (id: number) => void
}

let nextId = 1

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  push(message, kind = 'info') {
    const id = nextId++
    set({ toasts: [...get().toasts.slice(-2), { id, message, kind }] })
    setTimeout(() => get().dismiss(id), 2400)
  },
  dismiss(id) {
    set({ toasts: get().toasts.filter((t) => t.id !== id) })
  },
}))

/** 任意模块可直接调用的便捷 toast（client.ts 拦截器等非组件场景） */
export function toast(message: string, kind: ToastItem['kind'] = 'info'): void {
  useToastStore.getState().push(message, kind)
}
