import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'

// Flat config（ESLint 9/10）：@eslint/js recommended + typescript-eslint recommended
// + react-hooks recommended-latest。不引入 Prettier 到 ESLint（两者职责分离）。
export default tseslint.config(
  // 构建产物 / 打包器与工具配置不参与 lint
  { ignores: ['dist/', '*.config.ts', 'eslint.config.js'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  // ESLint 10 要求 plugins 为对象形式，用插件的 flat 变体（recommended 的等价 flat 导出）
  reactHooks.configs.flat.recommended,
  {
    // F-FE-16/29 整改：rules-of-hooks 与 refs 已恢复 error（诱因——use 前缀普通函数、
    // 条件 hook 调用、渲染期读写 ref——已修复，见 VoicePanel/CandidateCard/
    // SearchInput/AccountMenu/ArrangementView 等）。
    // 仍暂降级 warn 的规则：既有「effect 内拉数据」模式（拦截器统一 toast 口径），
    // 本批已清理可安全清理者，剩余告警清单见评审整改记录。
    rules: {
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
  {
    // 代码库既有约定：未使用的参数以下划线开头（如测试里的 (_v: string) => {}）
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
)
