import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';

// 字体（本地打包，unicode-range 分片按需加载）
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/noto-serif-sc/500.css';
import '@fontsource/noto-serif-sc/600.css';
import '@fontsource/noto-serif-sc/700.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';

import { palette, injectTokens } from './theme/tokens';
import App from './App';
import './styles/global.css';
import './styles/app.css';

// 首帧渲染前注入颜色 CSS 变量（FRONTEND.md §3.3 单一来源机制，无闪烁）
injectTokens();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ConfigProvider
          locale={zhCN}
          theme={{
            algorithm: theme.darkAlgorithm, // v1.2 深色体系
            cssVar: true,
            token: {
              // 与 tokens.ts 同源映射——AntD 默认色不得在任何位置漏出（铁律 4）
              colorPrimary: palette.primary,
              colorSuccess: palette.success,
              colorWarning: palette.warning,
              colorError: palette.danger,
              colorBgLayout: palette.surface,
              colorBgContainer: palette.surfaceRaised,
              colorBgElevated: palette.surfaceElevated,
              colorBorder: palette.border,
              colorBorderSecondary: palette.surfaceInset,
              colorText: palette.textMain,
              colorTextSecondary: palette.textSub,
              colorTextTertiary: palette.textDisabled,
              colorTextQuaternary: palette.textFaint,
              // 主色为中亮度低饱和，实底按钮文字用深字
              colorTextLightSolid: palette.surface,
              borderRadius: 8,
              fontFamily: "'Inter', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif",
            },
          }}
        >
          <App />
        </ConfigProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
