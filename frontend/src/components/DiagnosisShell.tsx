/**
 * 诊断壳（FRONTEND.md §4）：三页共享 Layout。
 * 职责：详情取数（轮询 hook）+ 页面守卫重定向（status→落点）+ 头部 + 步骤条 + 失败横幅。
 * 子页面通过 Outlet context 消费 detail。
 */

import { Navigate, Outlet, useLocation, useParams } from 'react-router-dom';
import { Spin } from 'antd';
import { useDiagnosis } from '../hooks/useDiagnosis';
import type { DiagnosisDetail } from '../api/types';
import StatusTag from './StatusTag';
import StepIndicator from './StepIndicator';
import FailureBanner from './FailureBanner';
import PageBackdrop from './PageBackdrop';

/** status → 允许停留的子路由段（''=工作台 / 'exec' / 'report'） */
function allowedSegment(status: string): '' | 'exec' | 'report' {
  if (status === 'done') return 'report';
  if (status === 'executing' || status === 'assembling' || status === 'failed_at(executing)' || status === 'failed_at(assembling)') return 'exec';
  return ''; // routed / ready / failed_at(routing|data) / created
}

export default function DiagnosisShell() {
  const { id } = useParams();
  const location = useLocation();
  const { data, isLoading, isError } = useDiagnosis(id);

  if (isLoading) {
    return (
      <div className="shell-loading">
        <Spin />
        <span className="cc-eyebrow">LOADING DIAGNOSIS</span>
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="shell-loading">
        <div className="cc-serif" style={{ fontSize: 'var(--font-h2)' }}>诊断不存在或已被删除</div>
        <a href="/">← 返回首页</a>
      </div>
    );
  }

  // 页面守卫：URL 段与 status 不符时重定向（T5 刷新恢复）
  const seg = location.pathname.endsWith('/exec') ? 'exec' : location.pathname.endsWith('/report') ? 'report' : '';
  const want = allowedSegment(data.status);
  if (seg !== want) {
    return <Navigate replace to={`/workspace/${data.diagnosis_id}${want ? `/${want}` : ''}`} />;
  }

  return (
    <div className="shell">
      {/* 全站背景动效层（fixed z:-1）——P1/P2/P3 三页共享，路由切换不重建 */}
      <PageBackdrop />
      <header className="shell-head">
        <div className="shell-head-left">
          <a className="shell-back" href="/">← 首页</a>
          <span className="cc-serif shell-title">{data.product_name}</span>
          <span className="ts-dim">· {data.category}</span>
          <StatusTag status={data.status} loading={data.status === 'executing'} />
        </div>
        <span className="cc-eyebrow">{data.diagnosis_id.toUpperCase()}</span>
      </header>
      <StepIndicator status={data.status} />
      <FailureBanner detail={data} />
      <Outlet context={{ detail: data } satisfies { detail: DiagnosisDetail }} />
    </div>
  );
}
