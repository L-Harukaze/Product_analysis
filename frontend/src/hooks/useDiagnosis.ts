/**
 * 诊断详情查询 hook（P-4 轮询纪律唯一实现点）：
 * status ∈ {executing, assembling} 时 2s 轮询，终态自动停（FRONTEND.md 铁律 3）。
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/diagnoses';
import type { DxStatus } from '../api/types';

export function useDiagnosis(id: string | undefined) {
  return useQuery({
    queryKey: ['dx', id],
    queryFn: () => api.getDiagnosis(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const s = query.state.data?.status as DxStatus | undefined;
      return s === 'executing' || s === 'assembling' ? 2000 : false;
    },
  });
}

/** 动作后统一失效详情缓存（守卫态变化立即反映） */
export function useInvalidateDx() {
  const qc = useQueryClient();
  return (id: string) => {
    void qc.invalidateQueries({ queryKey: ['dx', id] });
    void qc.invalidateQueries({ queryKey: ['dx-list'] });
  };
}
