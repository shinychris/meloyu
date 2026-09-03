import { describe, expect, it } from 'vitest'
import { renderToString } from 'react-dom/server'
import LangSwitch from './LangSwitch'
import { useI18nStore } from '../../i18n'

/** 语言切换下拉冒烟：SSR 初始态（菜单闭合）+ 触发器按当前 locale 显示代码 */
describe('LangSwitch 下拉', () => {
  it('默认(en)渲染 EN 触发器且整树零中文，菜单闭合', () => {
    useI18nStore.getState().setLocale('en')
    const html = renderToString(<LangSwitch />)
    expect(html).toContain('EN')
    expect(html).toContain('aria-label="Language"')
    expect(html).toContain('aria-expanded="false"')
    expect(html).not.toContain('role="listbox"') // 闭合态不渲染菜单
    expect(html).not.toMatch(/[\u4e00-\u9fff]/) // en 界面零中文（含 aria-label）
  })

  it('zh locale 触发器显示 ZH 代码，aria-label 本地化为中文', () => {
    useI18nStore.getState().setLocale('zh')
    const html = renderToString(<LangSwitch />)
    expect(html).toContain('ZH')
    expect(html).toContain('aria-label="语言"')
    useI18nStore.getState().setLocale('en') // 恢复默认，避免污染其他用例
  })
})
