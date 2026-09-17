/**
 * 失败横幅（FRONTEND.md §4.1）——三个恢复回路的可见入口（T6 + 3.4）。
 * 方法级失败不进横幅（留在 P2 方法卡，不传染原则）。
 */

import { useMutation } from '@tanstack/react-query';
import { Alert, Button } from 'antd';
import { api } from '../api/diagnoses';
import type { DiagnosisDetail, DxStage } from '../api/types';
import { useInvalidateDx } from '../hooks/useDiagnosis';

export default function FailureBanner({ detail }: { detail: DiagnosisDetail }) {
  const invalidate = useInvalidateDx();
  const id = detail.diagnosis_id;

  const recover = useMutation({
    mutationFn: async (stage: DxStage) => {
      if (stage === 'routing') return api.reroute(id);
      if (stage === 'executing') return api.execute(id);
      return api.reassemble(id);
    },
    onSuccess: () => invalidate(id),
  });

  const err = detail.error_detail;
  if (!err) return null;
  const stage = err.stage;

  const actions: Partial<Record<DxStage, { label: string; run: () => void }>> = {
    routing: { label: '重试产品分析', run: () => recover.mutate('routing') },
    executing: { label: '重新执行（全部重跑）', run: () => recover.mutate('executing') },
    assembling: { label: '重新装配报告', run: () => recover.mutate('assembling') },
    data: { label: '回提交区重试', run: () => window.scrollTo({ top: 9999, behavior: 'smooth' }) },
  };
  const act = actions[stage];

  return (
    <Alert
      className="shell-banner"
      type="error"
      showIcon
      message={`${stage === 'routing' ? '产品分析失败' : stage === 'data' ? '数据环节异常（系统问题，非数据被拒）' : stage === 'executing' ? '执行中断（系统问题）' : '报告装配失败'}`}
      description={
        <>
          <div className="mono-note">
            原始报错：{err.raw}
            {err.timeout !== '—' && <> · 超时：{err.timeout} · 已自动重试 {err.retries} 次 · {err.split_record}</>}
          </div>
          {act && (
            <Button size="small" danger loading={recover.isPending} onClick={act.run} style={{ marginTop: 8 }}>
              {act.label}
            </Button>
          )}
        </>
      }
    />
  );
}
