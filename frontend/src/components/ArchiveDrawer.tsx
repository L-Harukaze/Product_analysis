/**
 * 档案库 Drawer（Owner 微调 2026-09-16 新增；2026-09-17 S25③ 修正"改数不落库"；S28 扩 error 档）。
 * 冲突裁决 / L2 error 档阻断的修数入口：展示全部已入档数据，检出问题行（冲突或 error 档）标红可直接编辑。
 *
 * ⚠️ 整表提交约束（8.3 按表覆盖，必读）：提交给 /data 的每一个表都**被视为该表的最新全量快照**
 * ——后端会先作废该表旧行再写入。所以本地改了几行，也必须提交**该表的全部行**
 * （当前档案行 + 本地修改的合并结果）。只发改动行 = 未提交的行被覆盖删除 = 数据丢失。
 *
 * 未修改任何数据时的确认动作（S28 分叉，两条路径都必须保住）：
 * - 冲突场景 → 复用 verdict 端点留痕（"已查看，未修改"，11.3 幂等，曾由校验卡回归）
 * - 纯 error 档场景 → error 无"维持"语义（不可裁决），直接返回、不落库
 */

import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Alert, Button, Drawer, Input } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { api } from '../api/diagnoses';
import type { DiagnosisDetail } from '../api/types';
import { useInvalidateDx } from '../hooks/useDiagnosis';
import { tableLabel } from '../labels';

/** 解析冲突行引用（'表B 行 2' → B 表第 2 行，1-based） */
function parseRowRef(ref: string): { table: string; row: number } | null {
  const m = ref.match(/表([A-Z])\s*行\s*(\d+)/);
  return m ? { table: m[1], row: Number(m[2]) } : null;
}

export default function ArchiveDrawer({
  open,
  onClose,
  detail,
  onApplyFix,
}: {
  open: boolean;
  onClose: () => void;
  detail: DiagnosisDetail;
  /** 修数出口：把「整表修正稿」的 JSON 交给工作台预填提交区，由 Owner 核对后走 /data 提交 */
  onApplyFix: (payload: string) => void;
}) {
  const invalidate = useInvalidateDx();
  const id = detail.diagnosis_id;
  const conflict = detail.pending_conflicts?.[0];
  const blockingErrors = detail.blocking_errors ?? [];

  /** 本地编辑：`${table}-${row}-${field}` → 新值 */
  const [edits, setEdits] = useState<Record<string, string>>({});

  // 冲突行集合（表 → 行号集合）
  const conflictCells = useMemo(() => {
    const map = new Map<string, Set<number>>();
    (detail.pending_conflicts ?? []).forEach((c) =>
      c.rows.forEach((r) => {
        const p = parseRowRef(r);
        if (!p) return;
        map.set(p.table, (map.get(p.table) ?? new Set()).add(p.row));
      }),
    );
    return map;
  }, [detail.pending_conflicts]);

  // L2 error 档行集合（S28）：error 档场景没有 conflict，"红色行"= 不变式错误行（同构标红可编辑）
  const errorCells = useMemo(() => {
    const map = new Map<string, Set<number>>();
    (detail.blocking_errors ?? []).forEach((c) =>
      c.rows.forEach((r) => {
        const p = parseRowRef(r);
        if (!p) return;
        map.set(p.table, (map.get(p.table) ?? new Set()).add(p.row));
      }),
    );
    return map;
  }, [detail.blocking_errors]);

  const verdict = useMutation({
    mutationFn: () =>
      api.conflictVerdict(
        id,
        conflict!.id,
        Object.keys(edits).length > 0
          ? `已手动修正档案数据（${Object.keys(edits).length} 处修改）`
          : '已查看档案库，未修改数据',
      ),
    onSuccess: () => {
      setEdits({});
      invalidate(id);
      onClose();
    },
  });

  const tables = Object.entries(detail.archive_rows ?? {});
  const editedN = Object.keys(edits).length;

  /**
   * 整表修正稿（8.3 按表覆盖 → **必须发该表全部行**，不能只发改动行）。
   * 过程：取档案库该表的当前全量行 → 深拷贝 → 套用本地 edits → JSON 化。
   * 类型转换：Input 给的是字符串，数值字段必须还原成 number，否则 L1 会报"类型错误"打回。
   */
  const buildFixPayload = (): string => {
    const byTable = new Map<string, Record<string, unknown>[]>();
    Object.entries(edits).forEach(([key, raw]) => {
      const m = key.match(/^([A-Z]+)-(\d+)-(.+)$/);
      if (!m) return;
      const [, table, rowS, field] = m;
      const rowIdx = Number(rowS);
      if (!byTable.has(table)) {
        byTable.set(
          table,
          ((detail.archive_rows ?? {})[table] ?? []).map((r) => ({ ...r })),
        );
      }
      const row = byTable.get(table)?.[rowIdx];
      if (!row || !(field in row)) return;
      const original = row[field];
      if (typeof original === 'number') {
        const n = Number(raw);
        row[field] = Number.isFinite(n) ? n : original;
      } else {
        row[field] = raw;
      }
    });
    return JSON.stringify({ tables: Object.fromEntries(byTable) }, null, 2);
  };

  /** 确认：有修改 → 生成整表修正稿交给工作台预填（走 /data 提交）。
   *  无修改：冲突场景沿用 verdict 留痕（"已查看，未修改"，11.3 幂等）；
   *  纯 error 档场景无"维持"语义，直接返回、不落库（S28 分叉守卫） */
  const handleConfirm = () => {
    if (editedN > 0) {
      onApplyFix(buildFixPayload());
      return;
    }
    if (conflict) {
      verdict.mutate();
      return;
    }
    onClose();
  };

  return (
    <Drawer
      open={open}
      onClose={() => {
        setEdits({});
        onClose();
      }}
      width={680}
      title={
        <span className="cc-serif">数据档案库 · 手动更改</span>
      }
    >
      <div className="dim" style={{ marginBottom: 16 }}>
        系统采集入库的全部数据都在这里。<span style={{ color: 'var(--danger)' }}>红色行</span>是系统检出问题（冲突或数据错误）的数据——
        直接点击数值修改，确认后会生成该表的完整修正稿并填入提交区，核对后提交入档，再触发执行即可通过。
      </div>

      {conflict && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={`待处理冲突：${conflict.invariant}`}
          description={conflict.detail}
        />
      )}
      {!conflict && blockingErrors.length > 0 && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message={`待修正数据错误：${blockingErrors[0].invariant}`}
          description={blockingErrors.length > 1
            ? `${blockingErrors[0].detail}（共 ${blockingErrors.length} 处）`
            : blockingErrors[0].detail}
        />
      )}

      {tables.length === 0 && <div className="dim">暂无档案数据。</div>}

      <div className="arch-list">
        {tables.map(([tableId, rows]) => {
          const conflictRows = conflictCells.get(tableId) ?? new Set<number>();
          const errorRows = errorCells.get(tableId) ?? new Set<number>();
          return (
            <div key={tableId} className="cc-inset arch-table">
              <div className="arch-table-head">
                <span className="cc-serif">{tableLabel(tableId)}</span>
                <span className="dim">{rows.length} 行</span>
              </div>
              {rows.map((row, i) => {
                const isConflict = conflictRows.has(i + 1);
                const isError = errorRows.has(i + 1);
                const flagged = isConflict || isError;
                return (
                  <div key={i} className={`arch-row ${flagged ? 'is-conflict' : ''}`}>
                    <span className="arch-row-n">{i + 1}</span>
                    {isConflict && (
                      <span className="arch-conflict-badge">
                        <EditOutlined /> 冲突数据 · 可修改
                      </span>
                    )}
                    {!isConflict && isError && (
                      <span className="arch-conflict-badge">
                        <EditOutlined /> 错误数据 · 可修改
                      </span>
                    )}
                    <div className="arch-row-fields">
                      {Object.entries(row).map(([field, value]) => {
                        const key = `${tableId}-${i}-${field}`;
                        const editable = flagged && typeof value !== 'object';
                        return (
                          <div key={field} className="arch-field">
                            <span className="arch-field-k">{field}</span>
                            {editable ? (
                              <Input
                                size="small"
                                className="arch-field-input"
                                value={edits[key] ?? String(value)}
                                onChange={(e) => setEdits({ ...edits, [key]: e.target.value })}
                              />
                            ) : (
                              <span className="arch-field-v">{String(value)}</span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>

      <div className="arch-footer">
        <div className="dim">
          {editedN > 0
            ? `已修改 ${editedN} 处 → 确认后生成该表的完整修正稿（当前全部行 + 你的修改）填入提交区，`
              + '核对后点「提交校验」才真正入档（8.3：提交体 = 该表最新全量快照，旧行作废）'
            : conflict
              ? '未修改任何数据，确认即视为"已查看并认可现有数据"（按维持留痕）'
              : '未修改任何数据；数据错误没有"维持"选项，请修正后生成修正稿'}
        </div>
        <Button type="primary" loading={verdict.isPending} onClick={handleConfirm}>
          {editedN > 0 ? '生成整表修正稿，填入提交区' : conflict ? '确认未修改，返回工作台' : '返回工作台（未修改数据）'}
        </Button>
      </div>
    </Drawer>
  );
}
