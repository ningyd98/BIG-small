// Dashboard ESLint 配置：约束前端源码和测试代码风格，不读取密钥、不启动服务，也不连接任何真实硬件。
import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      'playwright-report/**',
      'test-results/**',
      'src/api/generated/schema.d.ts',
      '*.tsbuildinfo'
    ]
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh
    },
    rules: {
      // eslint-plugin-react-hooks 7.x expands its umbrella recommended preset
      // with React Compiler diagnostics. Keep the dashboard gate pinned to the
      // two stable runtime-safety rules that this repository previously enforced.
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }]
    }
  }
)
