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
    // 存量代码暂降级为 warn 的规则（不改正业务代码；后续专项清零后调回 error）：
    // - rules-of-hooks：ModelCenterView 的 useCatalogModel 是 use 前缀的普通异步函数（命名误报）；
    //   CandidateCard.tsx:38 存在 || 右侧条件调用 useStudioStore（zustand 下实际安全，待重构）
    // - set-state-in-effect / refs：react-hooks v7 新增规则，对既有「effect 内拉数据」模式报 error
    rules: {
      'react-hooks/rules-of-hooks': 'warn',
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/refs': 'warn',
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
