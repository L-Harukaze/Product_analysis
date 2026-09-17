/**
 * 四步指示器（FRONTEND.md §4 诊断壳）——状态机驱动，无会话态。
 */

import type { DxStatus } from '../api/types';
import { failedStage } from '../api/types';

const STEPS = ['路由', '数据准备', '执行', '报告'] as const;

type StepState = 'done' | 'current' | 'error' | 'todo';

export default function StepIndicator({ status }: { status: DxStatus }) {
  const failed = failedStage(status);
  const states: StepState[] = (() => {
    if (status === 'done') return ['done', 'done', 'done', 'current'];
    if (status === 'executing' || status === 'assembling') return ['done', 'done', 'current', 'todo'];
    if (status === 'routed' || status === 'ready') return ['done', 'current', 'todo', 'todo'];
    // failed_at(stage)
    if (failed === 'routing') return ['error', 'todo', 'todo', 'todo'];
    if (failed === 'data') return ['done', 'error', 'todo', 'todo'];
    if (failed === 'executing') return ['done', 'done', 'error', 'todo'];
    return ['done', 'done', 'error', 'todo']; // assembling 失败：装配挂事务 C 尾
  })();

  return (
    <div className="stepbar">
      {STEPS.map((label, i) => (
        <span key={label} className="stepbar-item">
          <span
            className={`stepbar-dot ${states[i] === 'done' ? 'is-done' : ''} ${
              states[i] === 'current' ? 'is-current' : ''
            } ${states[i] === 'error' ? 'is-error' : ''}`}
          >
            {states[i] === 'done' ? '✓' : states[i] === 'error' ? '✕' : i + 1}
          </span>
          <span
            className={`stepbar-label ${states[i] === 'current' ? 'is-current' : ''} ${
              states[i] === 'error' ? 'is-error' : ''
            } ${states[i] === 'todo' ? 'is-todo' : ''}`}
          >
            {label}
            {states[i] === 'error' ? '（失败）' : states[i] === 'current' ? '（你在这里）' : ''}
          </span>
          {i < STEPS.length - 1 && <span className="stepbar-line" />}
        </span>
      ))}
    </div>
  );
}
