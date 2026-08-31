import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { debounce, sanitizeQuery } from '../../lib/debounce'

interface SearchInputProps {
  /** 防抖后的查询词（仅用于 API 查询参数，绝不回写输入框） */
  onQueryChange: (q: string) => void
  delayMs?: number
  maxLength?: number
  placeholder?: string
}

/**
 * 作品库搜索框（模拟测试发现 #1 修复）。
 *
 * 根因形态：输入框 value 挂在视图级 state 上，防抖 400ms 后触发 setQ → 列表加载
 * → 视图整体重渲染，受控 value 与 DOM 选区在重渲染竞争中被重置/恢复，
 * 导致 Ctrl+A 后输入变追加、程序化清空失效。
 *
 * 修复：输入框自持本地即时 state（不依赖父级任何异步数据），React.memo 隔离
 * 父级 loading/items 等重渲染；防抖只作用于 onQueryChange 回调。清空按钮
 * 立即同步本地 state 并即时通知（跳过防抖），保证一键清空生效。
 */
function SearchInputImpl({ onQueryChange, delayMs = 400, maxLength = 50, placeholder }: SearchInputProps) {
  const [value, setValue] = useState('')
  const cbRef = useRef(onQueryChange)
  cbRef.current = onQueryChange

  const emit = useMemo(
    () => debounce((v: string) => cbRef.current(sanitizeQuery(v, maxLength)), delayMs),
    [delayMs, maxLength],
  )
  useEffect(() => () => emit.cancel(), [emit])

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValue(e.target.value)
    emit(e.target.value)
  }

  const onClear = () => {
    emit.cancel()
    setValue('')
    cbRef.current('') // 清空立即生效，不等防抖
  }

  return (
    <div className="relative inline-flex items-center">
      <input
        type="text"
        value={value}
        maxLength={maxLength}
        placeholder={placeholder ?? '搜索…'}
        aria-label="搜索"
        onChange={onChange}
        className="!w-[220px] !text-[12px] !pr-7"
        style={{ padding: '6px 10px' }}
      />
      {value !== '' && (
        <button
          type="button"
          aria-label="清空搜索"
          title="清空搜索"
          onClick={onClear}
          className="absolute right-1.5 w-5 h-5 flex items-center justify-center text-[11px] leading-none"
          style={{ color: 'var(--dim)' }}
        >
          <svg viewBox="0 0 16 16" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
          </svg>
        </button>
      )}
    </div>
  )
}

/** memo：父级列表加载/翻页等重渲染不再触碰本输入框（选区保持原生行为） */
const SearchInput = memo(SearchInputImpl)
export default SearchInput
