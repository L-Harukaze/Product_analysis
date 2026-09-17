/**
 * P1 数据工作台（FRONTEND.md §5）——routed/ready 长停留态（人肉断点 1+2）。
 * 左看右做：左=系统想清楚了什么（产品特征/分析方法/数据清单）；右=你要干的活（prompt/提交/历史）。
 * ready：触发执行；数据冲突面板（触发被拒=正常保护，非系统故障）。
 * Owner 微调 2026-09-16：术语全面用户语化；缺数清单展示全部所需数据（✓/✗）；
 * 冲突裁决=「手动更改（进档案库改数）/ 拒绝变更」；提交处理后清空输入框。
 */

import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert, Button, Drawer, Input, Table, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CheckCircleOutlined, CloseCircleOutlined, CopyOutlined, DatabaseOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { api } from '../api/diagnoses';
import type { DataError, DiagnosisDetail, FingerprintItem } from '../api/types';
import { useInvalidateDx } from '../hooks/useDiagnosis';
import { SAMPLE_OK_D, SAMPLE_OK_F, SAMPLE_REJECT_D } from '../mocks/fixtures';
import { SOURCE_LABELS, methodLabel, tableLabel } from '../labels';
import ArchiveDrawer from '../components/ArchiveDrawer';
import AnalysisHistoryCard from '../components/AnalysisHistoryCard';

export default function WorkspacePage() {
  const { detail } = useOutletContext<{ detail: DiagnosisDetail }>();
  const invalidate = useInvalidateDx();
  const id = detail.diagnosis_id;
  const isReady = detail.status === 'ready';
  // L2 error 档检出（必须修数的硬伤）：详情驱动——阻断卡片与提交区显示策略共用（S28）
  const blockingErrors = detail.blocking_errors ?? [];

  const [payload, setPayload] = useState('');
  // 档案库"手动更改"生成的整表修正稿提示（8.3：提交=该表整体覆盖，务必让 Owner 知道）
  const [fixHint, setFixHint] = useState<string | null>(null);
  const [fpOpen, setFpOpen] = useState<FingerprintItem | null>(null);
  const [conflictPanel, setConflictPanel] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);

  const prompt = useQuery({
    queryKey: ['dx', id, 'prompt'],
    queryFn: () => api.getCollectionPrompt(id),
    enabled: detail.status === 'routed',
    retry: 1, // T6：失败快速可见，不无限重试（2026-09-16 联调 404→永久"加载中"事故教训）
  });

  const submit = useMutation({
    mutationFn: () => api.submitData(id, payload),
    onSuccess: (res) => {
      invalidate(id);
      // Owner 微调：提交已被处理（入档或打回原因已注入新 prompt）→ 清空输入框，
      // 用户下一步是复制最新采集 prompt 重新取数
      setPayload('');
      setFixHint(null);
      // 校验完全通过 → 自动回到页面顶部（看清单 ✓ 与触发执行）
      if (res.accepted) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    },
    onError: (e) => {
      // T6：提交失败必须可见——静默失败曾表现为"按钮抖一下无响应"（2026-09-16 联调事故）
      const status = (e as { status?: number }).status;
      void message.error(
        status === 409 ? '当前状态不可提交数据（请刷新页面）' : `提交失败：${(e as Error).message}——请检查后端服务`,
      );
    },
  });

  const execute = useMutation({
    mutationFn: () => api.execute(id),
    onSuccess: () => invalidate(id),
    onError: (e) => {
      const err = e as {
        status?: number;
        body?: { detail?: { reason?: string; conflicts?: unknown[] } };
      };
      const detail409 = err.body?.detail;
      // 409 + 冲突清单 = 触发被拒（正常保护）→ 弹冲突面板
      if (err.status === 409 && (detail409?.conflicts?.length ?? 0) > 0) {
        setConflictPanel(true);
        invalidate(id);
        return;
      }
      if (err.status === 409) {
        // L2 error 档（或状态守卫）：不弹一闪而过的 message（S26④ 的"可见"在 S28 升级为
        // 结构化卡片）——invalidate 后由详情 blocking_errors 驱动常驻阻断卡片，
        // 含逐条明细与「手动更改」修数入口；状态守卫场景刷新后页面自动切换视图
        // （前端只在 ready 渲染触发按钮，能触发守卫 409 的都是页面数据过期的边缘情况）。
        invalidate(id);
        return;
      }
      // 非 409（网络/500）：提示查后端（T6：失败必须可见）
      void message.error(`触发执行失败：${(e as Error).message}——请检查后端服务`);
      invalidate(id);
    },
  });

  const verdict = useMutation({
    mutationFn: (cid: string) => api.conflictVerdict(id, cid, '拒绝变更：保留现有数据'),
    onSuccess: () => {
      invalidate(id);
      setConflictPanel(false);
    },
  });

  const copy = (text: string) => {
    void navigator.clipboard.writeText(text);
    void import('antd').then(({ message }) => message.success('已复制到剪贴板'));
  };

  const errCols: ColumnsType<DataError> = [
    { title: '数据', dataIndex: 'table', width: 200, render: (v: string) => (v === '-' ? '整体' : tableLabel(v)) },
    { title: '位置', dataIndex: 'row_index', width: 70, render: (v: number) => `第 ${v} 行` },
    { title: '字段', dataIndex: 'field', width: 130 },
    { title: '问题', dataIndex: 'error' },
  ];

  return (
    <div className="ws">
      {/* L2 error 档阻断卡片（S28）：常驻渲染（详情 blocking_errors 驱动，刷新不丢）——
          error 档无"维持"语义、必须修数，卡片给出逐条明细 + 「手动更改」修数入口 */}
      {isReady && blockingErrors.length > 0 && (
        <Alert
          className="ws-l2block"
          type="error"
          showIcon
          message={`发现 ${blockingErrors.length} 处数据不变式错误——修正后才能开始执行（数据质量保护，不是系统故障）`}
          description={
            <div className="ws-conflict-body">
              {blockingErrors.map((c) => (
                <div key={c.id} className="ws-conflict-item">
                  <div className="ws-conflict-text">
                    <b>{c.invariant}</b>
                    <div>{c.detail}</div>
                    <div className="dim">涉及数据：{c.rows.join('、')}</div>
                  </div>
                </div>
              ))}
              <div className="ws-conflict-actions">
                <Button size="small" type="primary" danger ghost icon={<DatabaseOutlined />} onClick={() => setArchiveOpen(true)}>
                  手动更改
                </Button>
              </div>
              <div className="dim">
                改数后生成整表修正稿，在右栏「提交校验」重新入档，再点「触发执行」重跑检查。
                本提示是最近一次检查结果，重新触发后才会刷新。
              </div>
            </div>
          }
        />
      )}

      {/* 数据冲突面板（触发被拒=数据保护，warning 语义非故障） */}
      {conflictPanel && detail.pending_conflicts && detail.pending_conflicts.length > 0 && (
        <Alert
          className="ws-conflict"
          type="warning"
          showIcon
          message={`发现 ${detail.pending_conflicts.length} 处数据冲突——处理完才能开始执行（这是数据保护，不是系统故障）`}
          description={
            <div className="ws-conflict-body">
              {detail.pending_conflicts.map((c) => (
                <div key={c.id} className="ws-conflict-item">
                  <div className="ws-conflict-text">
                    <b>{c.invariant}</b>
                    <div>{c.detail}</div>
                    <div className="dim">涉及数据：{c.rows.map((r) => r.replace('表', '').replace('行', ' 行')).join('、')}</div>
                  </div>
                  <div className="ws-conflict-actions">
                    <Button size="small" type="primary" ghost icon={<DatabaseOutlined />} onClick={() => setArchiveOpen(true)}>
                      手动更改
                    </Button>
                    <Button size="small" loading={verdict.isPending} onClick={() => verdict.mutate(c.id)}>
                      拒绝变更
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          }
        />
      )}

      <div className="ws-grid">
        {/* ———— 左栏：系统想清楚了什么 ———— */}
        <div className="ws-left">
          <section className="cc-card ws-card">
            <div className="ws-card-head">
              <div>
                <div className="cc-eyebrow">PRODUCT FINGERPRINT · 六大维度</div>
                <div className="ws-card-title cc-serif">产品特征判定</div>
              </div>
              <span className="dim">判定方式已逐项标注</span>
            </div>
            <div className="ws-fp-grid">
              {(detail.fingerprint ?? []).map((f, i) => (
                <button
                  key={f.dimension}
                  type="button"
                  className={`ws-fp ${f.source === 'L3 仲裁' ? 'is-l3' : ''}`}
                  onClick={() => f.detail && setFpOpen(f)}
                >
                  <div className="ws-fp-head">
                    <span className="cc-eyebrow">维度 {i + 1}</span>
                    <span className="ws-fp-src">{SOURCE_LABELS[f.source] ?? f.source}</span>
                  </div>
                  <div className="ws-fp-label">{f.label}</div>
                  <div className="ws-fp-value cc-serif">{f.value}</div>
                  {f.source === 'L3 仲裁' && <div className="ws-fp-more">★ 点开看 AI 的判断依据</div>}
                </button>
              ))}
            </div>
          </section>

          <section className="cc-card ws-card">
            <div className="ws-card-head">
              <div>
                <div className="cc-eyebrow">ANALYSIS PLAN</div>
                <div className="ws-card-title cc-serif">分析方法</div>
              </div>
              <span className="dim">不适用的也会说明为什么</span>
            </div>
            <table className="ws-table">
              <thead>
                <tr>
                  <th>分析域</th>
                  <th>方法</th>
                  <th>形态</th>
                  <th>为什么</th>
                </tr>
              </thead>
              <tbody>
                {(detail.activation_matrix ?? []).map((a, i) => (
                  <tr key={`${a.domain}-${a.method ?? 'na'}-${i}`}>
                    <td>{a.domain}</td>
                    <td>{a.method ? <span className="ws-method">{methodLabel(a.method)}</span> : <span className="dim">—</span>}</td>
                    <td>{a.method ? a.form : <span className="ws-form-na">不适用</span>}</td>
                    <td className="ws-reason">{a.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="cc-card ws-card">
            <div className="ws-card-head">
              <div>
                <div className="cc-eyebrow">DATA CHECKLIST</div>
                <div className="ws-card-title cc-serif">数据清单</div>
              </div>
              <span className="dim">
                {detail.missing_data?.filter((m) => m.status === 'missing').length ?? 0} 项待采集 · 共 {detail.missing_data?.length ?? 0} 项
              </span>
            </div>
            <div className="ws-missing">
              {(detail.missing_data ?? []).map((m) => (
                <div key={m.table} className={`ws-missing-item ${m.status === 'archived' ? 'is-ok' : 'is-miss'}`}>
                  <span>{m.status === 'archived' ? <CheckCircleOutlined /> : <CloseCircleOutlined />}</span>
                  <span>{m.name}</span>
                  <span className="dim">{m.status === 'archived' ? '已采集' : '待采集'}</span>
                </div>
              ))}
            </div>
            {isReady && (
              <Alert
                className="ws-ready-tip"
                type="success"
                showIcon
                message="数据已齐备——核对无误后，在右栏点击「触发执行」开始分析。"
                description={
                  <span className="dim">
                    {detail.archive_summary?.length
                      ? `本产品档案已预建档（${detail.archive_summary.length} 张表已入档），`
                        + '缺数清单为空 → 按 2.2 跳过采集步骤，直接停在可执行状态。'
                      : '缺数清单为空 → 按 2.2 跳过采集步骤，直接停在可执行状态。'}
                    {' '}触发执行时会自动校验数据一致性（L2），发现问题会明确提示并给出修正入口。
                  </span>
                }
              />
            )}
          </section>
        </div>

        {/* ———— 右栏：你要干的活 ———— */}
        <div className="ws-right">
          {isReady && (
            <section className="cc-card ws-card ws-execute-card">
              <div className="cc-eyebrow">READY · 开始分析</div>
              <div className="ws-execute-row">
                <div className="ws-execute-text">
                  <div className="ws-card-title cc-serif">触发执行</div>
                  <div className="dim">系统将并行运行上表列出的分析方法，全程自动推进</div>
                </div>
                <Button
                  type="primary"
                  size="large"
                  icon={<ThunderboltOutlined />}
                  loading={execute.isPending}
                  onClick={() => execute.mutate()}
                >
                  触发执行
                </Button>
              </div>
              {detail.pending_conflicts && detail.pending_conflicts.length > 0 && (
                <div className="warn-inline" style={{ marginTop: 8 }}>
                  ⚠ 有 {detail.pending_conflicts.length} 处数据冲突未处理——需要先处理（在上方冲突面板操作），才能开始执行。
                </div>
              )}
            </section>
          )}

          {detail.status === 'routed' && (
            <section className="cc-card ws-card">
              <div className="ws-card-head">
                <div>
                  <div className="cc-eyebrow">COLLECTION PROMPT</div>
                  <div className="ws-card-title cc-serif">采集 Prompt</div>
                </div>
                <Button size="small" icon={<CopyOutlined />} onClick={() => copy(prompt.data?.prompt ?? '')} disabled={!prompt.data}>
                  复制全文
                </Button>
              </div>
              {prompt.isError ? (
                <Alert
                  type="error"
                  showIcon
                  message="采集 Prompt 获取失败"
                  description="后端没有返回 Prompt。请重试；若持续失败，说明前后端契约不对齐，需检查后端日志。"
                  style={{ marginBottom: 8 }}
                  action={<Button size="small" danger onClick={() => void prompt.refetch()}>重试</Button>}
                />
              ) : (
                <div className="cc-inset ws-prompt">
                  <pre>{prompt.data?.prompt ?? '加载中…'}</pre>
                </div>
              )}
              <div className="dim" style={{ marginTop: 8 }}>
                把这段话整段复制给豆包（已接入数据源），它会帮你采集清单里缺的数据。被拒后这里会自动更新，带上具体错误原因——你不用自己转述。
              </div>
            </section>
          )}

          {/* 11.3 修数路径的提交区显示策略（S28 / P0-2 修订）：
              ① routed 态=采集循环常驻；
              ② ready 态**仅在有修数动机时**显示——冲突待裁决（pending_conflicts_n>0，
                 含"手动更改"生成的修正稿提交）或 error 档阻断待修（blocking_errors>0）；
              ③ 普通 ready（无冲突无错误）隐藏输入区，防"手滑重新提交旧表 = 无声覆盖好档案"
                 （8.3 按表覆盖语义下，S25① 刚堵上的数据丢失口子不能从 UX 侧再开一条）；
              ④ error 档场景的提交区是修数唯一出口（阻断卡片即指向这里），必须保留。 */}
          {(detail.status === 'routed'
            || (detail.status === 'ready'
              && ((detail.pending_conflicts_n ?? 0) > 0 || blockingErrors.length > 0))) && (
            <section className="cc-card ws-card">
              <div className="ws-card-head">
                <div>
                  <div className="cc-eyebrow">SUBMIT DATA</div>
                  <div className="ws-card-title cc-serif">提交豆包返回</div>
                </div>
                <span className="dim">
                  {detail.status === 'ready'
                    ? '档案已齐备 · 可提交修正稿（8.3：提交体 = 该表最新全量快照）'
                    : '可多次提交 · 全程留痕'}
                </span>
              </div>
              {fixHint && (
                <div className="cc-inset" style={{ marginBottom: 8 }}>
                  {fixHint}
                </div>
              )}
              <Input.TextArea
                className="ws-textarea"
                rows={6}
                value={payload}
                onChange={(e) => setPayload(e.target.value)}
                placeholder="粘贴豆包返回的 JSON 原文…"
              />
              <div className="ws-submit-row">
                <Button type="primary" loading={submit.isPending} disabled={!payload.trim()} onClick={() => submit.mutate()}>
                  提交校验
                </Button>
                <span className="dim">提交后立即校验，无需等待</span>
                <span className="ws-samples">
                  <span className="dim">演示辅助：</span>
                  <button type="button" className="ws-sample" onClick={() => setPayload(SAMPLE_OK_D)}>填入示例：竞品价格带（合格）</button>
                  <button type="button" className="ws-sample" onClick={() => setPayload(SAMPLE_REJECT_D)}>填入示例：竞品价格带（含错误）</button>
                  <button type="button" className="ws-sample" onClick={() => setPayload(SAMPLE_OK_F)}>填入示例：生态锁定（合格）</button>
                </span>
              </div>
              {submit.data && !submit.data.accepted && (
                <div className="ws-reject cc-inset">
                  <div className="ws-reject-title">✕ 校验未通过——具体错误如下，请让豆包修正后重新提交</div>
                  <div className="ws-reject-scroll">
                    <Table<DataError> size="small" columns={errCols} dataSource={submit.data.errors} rowKey={(r) => `${r.table}-${r.row_index}-${r.field}`} pagination={false} />
                  </div>
                </div>
              )}
              {submit.data?.accepted && (
                <Alert type="success" showIcon message="数据已入库" description={`数据清单已刷新${detail.missing_data?.every((m) => m.status === 'archived') ? ' · 清单已全部勾选，可以触发执行了' : ''}`} style={{ marginTop: 12 }} />
              )}
            </section>
          )}

          <section className="cc-card ws-card">
            <div className="ws-card-head">
              <div>
                <div className="cc-eyebrow">HISTORY</div>
                <div className="ws-card-title cc-serif">提交历史</div>
              </div>
              <span className="dim">{detail.submissions?.length ?? 0} 次</span>
            </div>
            {(detail.submissions ?? []).length === 0 && <div className="dim">暂无提交记录。</div>}
            <div className="ws-history ws-history-scroll">
              {(detail.submissions ?? []).map((s) => (
                <div key={s.n} className={`ws-history-item ${s.accepted ? 'is-ok' : 'is-bad'}`}>
                  <span className="ws-history-n">#{s.n}</span>
                  <span>{s.accepted ? '✓ 已入库' : '✕ 被拒'}</span>
                  <span className="dim">
                    {s.table && s.table !== '-' ? tableLabel(s.table) : '整体格式'}
                    {s.accepted ? ` · ${s.rows ?? 0} 行` : ` · ${s.errors?.length ?? 0} 处错误`}
                  </span>
                  <span className="dim">{new Date(s.at).toLocaleTimeString('zh-CN')}</span>
                </div>
              ))}
            </div>
          </section>

          {/* 完整分析历史：右栏收尾，flex 自动延伸至与左栏数据清单底部对齐 */}
          <AnalysisHistoryCard detail={detail} />
        </div>
      </div>

      {/* 产品特征判定依据 Drawer（AI 仲裁留痕） */}
      <Drawer
        open={!!fpOpen}
        onClose={() => setFpOpen(null)}
        width={420}
        title={
          fpOpen && (
            <span className="cc-serif">
              {fpOpen.label} · {fpOpen.value}
            </span>
          )
        }
      >
        {fpOpen?.detail && (
          <div className="ws-fp-drawer">
            <div className="ws-fp-drawer-row">
              <span className="cc-eyebrow">判定结果 </span>
              <span className="ws-fp-value cc-serif" style={{ fontSize: 'var(--font-h1)' }}>{fpOpen.value}</span>
            </div>
            <div className="ws-fp-drawer-row">
              <span className="cc-eyebrow">判断理由</span>
              <p>{fpOpen.detail.reason}</p>
            </div>
            <div className="ws-fp-drawer-row">
              <span className="cc-eyebrow">参照依据·先例/锚点</span>
              <ul>
                {fpOpen.detail.precedents.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
            <div className="ws-fp-drawer-row">
              <span className="cc-eyebrow">置信度</span>
              <span className="ws-fp-conf">{fpOpen.detail.confidence}</span>
            </div>
            <div className="dim" style={{ marginTop: 16 }}>
              AI 带着品类证据做出这段判断，结果已冻结存档——可复查、可追溯，不会悄悄变。
            </div>
          </div>
        )}
      </Drawer>

      {/* 档案库 Drawer（冲突裁决=手动更改 → 生成整表修正稿预填提交区，由 Owner 核对后走 /data 提交） */}
      <ArchiveDrawer
        open={archiveOpen}
        onClose={() => setArchiveOpen(false)}
        detail={detail}
        onApplyFix={(p: string) => {
          setPayload(p);
          setFixHint(
            '已生成整表修正稿并填入下方输入框：这是该表的完整行集（当前档案行 + 你的修改），'
            + '核对后点「提交校验」。提交即该表整体覆盖入档（8.3），随后触发执行时系统会重跑 L2 校验，问题消失即放行。',
          );
          setArchiveOpen(false);
          requestAnimationFrame(() => {
            document
              .querySelector('.ws-textarea')
              ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
          });
        }}
      />
    </div>
  );
}
