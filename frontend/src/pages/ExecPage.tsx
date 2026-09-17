/**
 * P2 执行进度（FRONTEND.md §5）——executing/assembling，唯一轮询页（轮询在 Shell hook）。
 * 管道条（数据→N方法并行→质检→装配→报告）+ 方法卡片网格。
 * Owner 微调 2026-09-16：方法失败时停住推进（人肉断点）——用户须选择
 * 「重试」（携带上轮错误经验重跑）或「跳过」（报告中登记为降级），
 * 全部处理完才继续装配与报告。错误经验沉淀到系统缺陷清单。
 */

import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Alert, Button } from 'antd';
import { ForwardOutlined, RedoOutlined } from '@ant-design/icons';
import { api } from '../api/diagnoses';
import type { DiagnosisDetail, MethodError, ProgressMethod } from '../api/types';
import { useInvalidateDx } from '../hooks/useDiagnosis';
import { methodLabel } from '../labels';

/** 方法卡 phase 徽标（非状态机枚举，独立小徽标） */
function PhaseBadge({ phase, handled }: { phase: ProgressMethod['phase']; handled?: ProgressMethod['handled'] }) {
  const map: Record<string, { cls: string; label: string; spin?: boolean }> = {
    pending: { cls: 'is-pending', label: '排队中' },
    done: { cls: 'is-done', label: handled === 'retried' ? '✓ 重试成功' : '✓ 完成' },
    failed: { cls: 'is-failed', label: '✕ 失败' },
  };
  const running = phase.startsWith('running');
  const cfg = running
    ? { cls: 'is-running', label: handled === 'retried' ? '重试中…' : `分析中 ${phase.slice(phase.indexOf('(') + 1, -1)}`, spin: true }
    : (map[phase] ?? map.pending!);
  return (
    <span className={`exec-badge ${cfg.cls}`}>
      {cfg.spin && <span className="staged-spin" style={{ width: 10, height: 10 }} />}
      {cfg.label}
    </span>
  );
}

function ErrorPanel({ error }: { error: MethodError }) {
  return (
    <div className="cc-inset exec-error">
      <div className="exec-error-title">错误详情</div>
      <div className="mono-note">超时上限：{error.timeout}</div>
      <div className="mono-note">已自动重试：{error.retries} 次</div>
      <div className="mono-note">拆轮记录：{error.split_record}</div>
      <div className="mono-note">原始报错：{error.raw}</div>
    </div>
  );
}

export default function ExecPage() {
  const { detail } = useOutletContext<{ detail: DiagnosisDetail }>();
  const invalidate = useInvalidateDx();
  const id = detail.diagnosis_id;
  const [expanded, setExpanded] = useState<string | null>(null);
  const progress = detail.progress;
  const isAssembling = detail.status === 'assembling';

  const retry = useMutation({
    mutationFn: (method: string) => api.retryMethod(id, method),
    onSuccess: () => invalidate(id),
  });
  const skip = useMutation({
    mutationFn: (method: string) => api.skipMethod(id, method),
    onSuccess: () => invalidate(id),
  });

  if (!progress && !isAssembling) {
    return <div className="page-pad dim">等待执行启动…</div>;
  }

  const methods = progress?.methods ?? [];
  const total = progress?.total_n ?? 0;
  const done = progress?.done_n ?? 0;
  const qc = methods.find((m) => m.method.startsWith('QC'));
  const qcRunning = qc?.phase.startsWith('running') ?? false;
  // 失败且未处置的方法（推进被阻断）
  const unhandledFails = methods.filter((m) => m.phase === 'failed' && !m.handled);
  const handledFails = methods.filter((m) => m.phase === 'failed' && m.handled);

  // 管道条状态
  const pipe = [
    { label: '数据档案', state: 'done' },
    { label: `方法 ${done}/${total} · 并行`, state: done === 0 ? 'pending' : done === total ? 'done' : 'running' },
    { label: qc ? `质检 ${qc.phase === 'done' ? '✓' : '…'}` : '质检', state: qc?.phase === 'done' ? 'done' : qcRunning ? 'running' : 'pending' },
    { label: '装配报告', state: isAssembling ? 'running' : detail.status === 'done' ? 'done' : 'pending' },
    { label: '完成', state: detail.status === 'done' ? 'done' : 'pending' },
  ];

  return (
    <div className="exec">
      {/* 失败停顿横幅：有未处置的失败方法 → 推进被阻断，用户须选择 */}
      {unhandledFails.length > 0 && (
        <Alert
          className="exec-pause"
          type="warning"
          showIcon
          message={`有 ${unhandledFails.length} 个方法执行失败——系统已暂停推进，请在下方卡片选择「重试」或「跳过`+"」"}
          description={
            <>
              <div>重试：AI 会带着这次失败的错误经验重跑一遍，通常能修复问题；错误原因会沉淀到系统缺陷清单，下次诊断自动规避。</div>
              <div>跳过：放弃该方法（不阻塞其他方法），报告中会如实登记"该方法未完成"。</div>
            </>
          }
        />
      )}
      {unhandledFails.length === 0 && handledFails.length > 0 && !isAssembling && (
        <Alert
          className="exec-pause"
          type="info"
          showIcon
          message={`失败方法已全部处理（重试/跳过）——其余方法收尾后自动进入装配`}
        />
      )}

      {/* 管道条：数据 → [N 方法并行] → 质检 → 装配 → 报告 */}
      <div className="cc-card exec-pipe">
        {pipe.map((n, i) => (
          <span key={n.label} className="exec-pipe-seg">
            <span className={`exec-pipe-node ${n.state === 'done' ? 'is-done' : ''} ${n.state === 'running' ? 'is-running' : ''}`}>
              {n.state === 'done' ? '✓ ' : n.state === 'running' ? '◐ ' : '○ '}
              {n.label}
            </span>
            {i < pipe.length - 1 && <span className="exec-pipe-arrow">→</span>}
          </span>
        ))}
      </div>

      {isAssembling ? (
        <div className="cc-card exec-assembling">
          <div className="cc-eyebrow">ASSEMBLING</div>
          <div className="cc-serif exec-assembling-title">报告装配中…</div>
          <div className="dim">
            正在把各方法的分析结果装配成完整报告：分七个领域逐段撰写 → 完整性检查 → 数字一致性校验。
            页面会自动刷新，装配完成后进入报告页。
          </div>
          <div className="exec-skeleton">
            <span /><span /><span /><span /><span /><span /><span />
          </div>
        </div>
      ) : (
        <>
          <div className="exec-summary dim">总进度：{done}/{total} 个方法已完成</div>
          <div className="exec-grid">
            {methods.map((m) => {
              const isFail = m.phase === 'failed';
              const isQC = m.method.startsWith('QC');
              const needsAction = isFail && !m.handled;
              return (
                <div key={m.method} className={`cc-card exec-card ${isFail ? 'is-fail' : ''}`}>
                  <div className="exec-card-head">
                    <span className="cc-serif exec-card-name">{methodLabel(m.method)}</span>
                    <PhaseBadge phase={m.phase} handled={m.handled} />
                  </div>
                  <div className="dim exec-card-hint">
                    {isQC
                      ? '对各方法的分析结果做自动质检'
                      : needsAction
                        ? '执行失败——等待你选择重试或跳过'
                        : m.phase.startsWith('running')
                          ? m.handled === 'retried'
                            ? '已注入上轮错误经验，正在重跑'
                            : '分析进行中'
                          : m.phase === 'pending'
                            ? '排队等待'
                            : m.phase === 'done'
                              ? m.handled === 'retried'
                                ? '重试成功 · 错误经验已沉淀到系统缺陷清单（下次诊断自动规避）'
                                : '已完成'
                              : m.handled === 'skipped'
                                ? '已跳过——将在报告中如实登记"该方法未完成"'
                                : ''}
                  </div>
                  {isFail && m.error && (
                    <>
                      <button type="button" className="exec-error-toggle" onClick={() => setExpanded(expanded === m.method ? null : m.method)}>
                        {expanded === m.method ? '收起错误详情' : '展开错误详情 ▾'}
                      </button>
                      {expanded === m.method && <ErrorPanel error={m.error} />}
                      {needsAction && (
                        <div className="exec-fail-actions">
                          <Button
                            size="small"
                            type="primary"
                            icon={<RedoOutlined />}
                            loading={retry.isPending && retry.variables === m.method}
                            onClick={() => retry.mutate(m.method)}
                          >
                            重试
                          </Button>
                          <Button
                            size="small"
                            icon={<ForwardOutlined />}
                            loading={skip.isPending && skip.variables === m.method}
                            onClick={() => skip.mutate(m.method)}
                          >
                            跳过
                          </Button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
