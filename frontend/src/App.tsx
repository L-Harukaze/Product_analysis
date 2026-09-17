/**
 * 路由骨架（FRONTEND.md §4）：
 * /                        P0 首页
 * /workspace/:id           P1 数据工作台（routed/ready）
 * /workspace/:id/exec      P2 执行进度（executing/assembling，唯一轮询页）
 * /workspace/:id/report    P3 报告与评测（done）
 * /__tokens                Token 试色页（dev-only，不进生产构建）
 */

import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Spin } from 'antd';
import DiagnosisShell from './components/DiagnosisShell';
import HomePage from './pages/HomePage';
import WorkspacePage from './pages/WorkspacePage';
import ExecPage from './pages/ExecPage';
import ReportPage from './pages/ReportPage';

const TokenSheet = import.meta.env.DEV
  ? lazy(() => import('./pages/TokenSheet'))
  : null;

export default function App() {
  return (
    <Suspense fallback={<div className="shell-loading"><Spin /></div>}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/workspace/:id" element={<DiagnosisShell />}>
          <Route index element={<WorkspacePage />} />
          <Route path="exec" element={<ExecPage />} />
          <Route path="report" element={<ReportPage />} />
        </Route>
        {TokenSheet && <Route path="/__tokens" element={<TokenSheet />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
