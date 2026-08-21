import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider, theme as antdTheme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import enUS from 'antd/locale/en_US'
import App from './App.tsx'
import 'antd/dist/reset.css'
import './index.css'
import './theme-dark.css'
import './i18n'
import './services/openapi'
import { useAppStore } from './store/useAppStore'

const RootApp: React.FC = () => {
  const language = useAppStore((state) => state.language)
  const antdLocale = language === 'en-US' ? enUS : zhCN

  return (
    <ConfigProvider
      locale={antdLocale}
      theme={{
        algorithm: antdTheme.darkAlgorithm,
        token: {
          // 猫叔的短剧工作台 · 暗色专业创作台（琥珀金强调色）
          colorPrimary: '#e8a33d',
          colorInfo: '#5a8fd1',
          colorSuccess: '#4ea87b',
          colorWarning: '#e8a33d',
          colorError: '#d16a5a',
          colorTextBase: '#eceef1',
          colorBgBase: '#0d0f12',
          colorBgLayout: '#0d0f12',
          colorBgContainer: '#16191e',
          colorBgElevated: '#1c2027',
          colorBorder: '#282e37',
          colorBorderSecondary: '#1f242b',
          borderRadius: 10,
          fontSize: 14,
          fontFamily:
            '"Inter", "DM Sans", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
        },
        components: {
          Layout: {
            headerBg: '#16191e',
            siderBg: '#16191e',
            bodyBg: '#0d0f12',
          },
          Menu: {
            itemSelectedBg: 'rgba(232, 163, 61, 0.12)',
            itemSelectedColor: '#e8a33d',
          },
          Card: { colorBorderSecondary: '#282e37' },
          Button: { primaryShadow: 'none' },
        },
      }}
    >
      <App />
    </ConfigProvider>
  )
}

class AppErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  state = { hasError: false, error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError && this.state.error) {
      return (
        <div style={{ padding: 24, fontFamily: 'sans-serif' }}>
          <h2>页面加载出错</h2>
          <pre style={{ color: '#c00', overflow: 'auto' }}>
            {this.state.error.message}
          </pre>
        </div>
      )
    }
    return this.props.children
  }
}

function renderApp() {
  const root = document.getElementById('root')
  if (!root) return
  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <AppErrorBoundary>
        <RootApp />
      </AppErrorBoundary>
    </React.StrictMode>,
  )
}

// 先立即渲染，避免 MSW 启动阻塞导致白屏
renderApp()

async function enableMocking() {
  if (import.meta.env.VITE_USE_MOCK !== 'true') {
    return
  }
  try {
    const { worker } = await import('./mocks/browser')
    await worker.start({ onUnhandledRequest: 'bypass' })
  } catch (error) {
    console.error('MSW start failed:', error)
  }
}

void enableMocking()

