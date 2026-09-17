/**
 * P3 报告与评测（FRONTEND.md §5）——done 终态，纵向长页。
 * 信任链顺序：总览 → 逐域证据 → 自曝短板（诚实性区）→ 外部评测。
 * Owner 微调 2026-09-16：术语用户语化（方法名/四层结构/质检档位）；
 * 长文本按 \n\n 分段渲染，保持结构清晰。
 */

import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Anchor, Button, Drawer, Input, Tag } from 'antd';
import { api } from '../api/diagnoses';
import type { ClaimInput, DiagnosisDetail, QCVerdict, ReportResponse } from '../api/types';
import EChart from '../components/EChart';
import { SAMPLE_CLAIMS } from '../mocks/fixtures';
import { methodLabel } from '../labels';

const VERDICT_COLOR: Record<QCVerdict, string> = {
  pass: 'var(--success)',
  warn: 'var(--warning-text)',
  fail: 'var(--danger)',
};

const VERDICT_TEXT: Record<QCVerdict, string> = {
  pass: '通过',
  warn: '存疑',
  fail: '不符',
};

/** 长文本分段渲染（\n\n 分段，段内换行转 <br/>） */
function RichText({ text }: { text: string }) {
  return (
    <>
      {text.split(/\n\n+/).map((p, i) => (
        <p key={i} className={`rp-p ${i === 0 ? 'is-lead' : ''}`}>
          {p.split('\n').map((line, j) => (
            <span key={j}>
              {j > 0 && <br />}
              {line}
            </span>
          ))}
        </p>
      ))}
    </>
  );
}

function EvidenceTag({ strength }: { strength: string }) {
  return (
    <span className={`rp-evi is-${strength === '官方' ? 'official' : strength === '第三方' ? 'third' : 'est'}`}>
      证据：{strength}
    </span>
  );
}

/** 四层诊断卡：事实依据 → 机制解释 → 量化结论 → 行动建议 */
function ItemCard({ item }: { item: ReportResponse['domains'][number]['items'] extends (infer T)[] | undefined ? T : never }) {
  return (
    <div className="cc-inset rp-item">
      <div className="rp-item-head">
        <span className="ws-method">{methodLabel(item.method)}</span>
        <EvidenceTag strength={item.evidence_strength} />
      </div>
      <div className="rp-layer">
        <span className="rp-layer-k">事实依据</span>
        <div className="rp-layer-v"><RichText text={item.L1_fact} /></div>
      </div>
      <div className="rp-layer">
        <span className="rp-layer-k">机制解释</span>
        <div className="rp-layer-v"><RichText text={item.L2_mechanism} /></div>
      </div>
      <div className="rp-layer">
        <span className="rp-layer-k">量化结论</span>
        <div className="rp-layer-v"><RichText text={item.L3_quantification} /></div>
      </div>
      <div className="rp-layer">
        <span className="rp-layer-k">行动建议</span>
        <div className="rp-layer-v"><RichText text={item.L4_prescription} /></div>
      </div>
      <div className="rp-confounder">混淆检查：{item.confounder_check}</div>
    </div>
  );
}

export default function ReportPage() {
  const { detail } = useOutletContext<{ detail: DiagnosisDetail }>();
  const id = detail.diagnosis_id;
  const qc = useQueryClient();

  const report = useQuery({ queryKey: ['dx', id, 'report'], queryFn: () => api.getReport(id) });
  const evaluation = useQuery({ queryKey: ['dx', id, 'evaluation'], queryFn: () => api.getEvaluation(id) });

  const [qcDrawer, setQcDrawer] = useState(false);
  const [claims, setClaims] = useState<ClaimInput[]>(SAMPLE_CLAIMS);

  const qcVerdict = useMutation({
    mutationFn: ({ qid, verdict }: { qid: string; verdict: '维持' | '修正' }) => api.qcVerdict(id, qid, verdict),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['dx', id, 'report'] });
    },
  });

  const submitClaims = useMutation({
    mutationFn: () => api.submitClaims(id, claims),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['dx', id, 'evaluation'] });
    },
  });

  const claimVerdict = useMutation({
    mutationFn: ({ cid, verdict }: { cid: string; verdict: '外部正确' | '我方正确' }) =>
      api.claimVerdict(id, cid, verdict),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['dx', id, 'evaluation'] });
    },
  });

  if (report.isLoading) {
    return <div className="page-pad dim">报告加载中…</div>;
  }
  if (!report.data) {
    return <div className="page-pad dim">报告不可用（当前状态未完成）。</div>;
  }
  const r = report.data;
  const qcCount = (v: QCVerdict) => r.qc.filter((q) => q.verdict === v).length;
  const activeDomains = r.domains.filter((d) => d.status === 'active');
  const domainName = (title: string) => title.split(' ').slice(1).join(' ') || title;

  return (
    <div className="rp">
      {/* 左侧锚点目录 */}
      <aside className="rp-toc">
        <div className="cc-eyebrow" style={{ marginBottom: 12 }}>CONTENTS</div>
        <Anchor
          affix={false}
          items={[
            ...r.domains.map((d) => ({ key: d.domain_id, href: `#rp-${d.domain_id}`, title: domainName(d.title) })),
            { key: 'honesty', href: '#rp-honesty', title: '冲突 / 降级 / 局限' },
            { key: 'eval', href: '#rp-eval', title: '外部观点对照' },
          ]}
        />
      </aside>

      <div className="rp-main">
        {/* ———— 报告头 ———— */}
        <header className="cc-card rp-head">
          <div className="cc-eyebrow">DIAGNOSIS REPORT · {id.toUpperCase()}</div>
          <h1 className="cc-serif rp-title">{detail.product_name} · 经济学诊断报告</h1>
          <div className="dim">
            覆盖 {activeDomains.length}/{r.domains.length} 个分析域 · 共 {activeDomains.reduce((n, d) => n + (d.items?.length ?? 0), 0)} 条诊断结论 · 每条结论的证据强度已逐条标注
          </div>
          <div className="rp-qc-summary">
            <span className="dim">数字质检汇总（点击查看详情并裁决）：</span>
            {(['pass', 'warn', 'fail'] as QCVerdict[]).map((v) => (
              <button key={v} type="button" className={`rp-qc-chip is-${v}`} onClick={() => setQcDrawer(true)}>
                {VERDICT_TEXT[v]} {qcCount(v)}
              </button>
            ))}
          </div>
        </header>

        {/* ———— 域章节 ———— */}
        {r.domains.map((d) => (
          <section key={d.domain_id} id={`rp-${d.domain_id}`} className="cc-card rp-domain">
            <div className="rp-domain-head">
              <span className="cc-serif rp-domain-title">
                {domainName(d.title)}
                <span className="rp-domain-id">{d.domain_id}</span>
              </span>
              <span className={`rp-domain-badge is-${d.status}`}>
                {d.status === 'active' ? '✓ 已分析' : d.status === 'weak' ? '◐ 弱适用（数据不足）' : '○ 不适用'}
              </span>
            </div>
            {d.status === 'active' ? (
              <>
                {(d.items ?? []).map((item, i) => (
                  <ItemCard key={i} item={item} />
                ))}
                {r.charts
                  .filter((c) => (d.items ?? []).some((it) => it.chart_refs.includes(c.chart_id)))
                  .map((c) => (
                    <div key={c.chart_id} className="rp-chart">
                      <div className="dim" style={{ marginBottom: 8 }}>{c.note}</div>
                      <EChart option={c.option as never} height={260} />
                    </div>
                  ))}
              </>
            ) : (
              <div className={`rp-placeholder ${d.status === 'weak' ? 'is-weak' : 'is-na'}`}>
                {d.status === 'not_applied' ? '○ ' : '◐ '}
                {d.note}
                <div className="dim" style={{ marginTop: 6 }}>
                  {d.status === 'weak' ? '数据不足时如实降级并说明原因——不编造数字' : '「为什么不做」本身也是分析结论的一部分'}
                </div>
              </div>
            )}
          </section>
        ))}

        {/* ———— 诚实性区（自曝短板）———— */}
        <section id="rp-honesty" className="cc-card rp-domain rp-honesty">
          <div className="cc-eyebrow">CONFLICTS · DOWNGRADES · LIMITATIONS</div>
          <div className="rp-domain-title cc-serif">冲突仲裁记录 · 未完成方法 · 分析局限</div>
          <div className="rp-honesty-block">
            <div className="rp-honesty-k">分析结论间冲突的仲裁记录（败方降级保留）</div>
            <RichText text={r.conflict_log} />
          </div>
          <div className="rp-honesty-block">
            <div className="rp-honesty-k">人工裁决记录</div>
            <RichText text={r.l2_conflict_notes} />
          </div>
          <div className="rp-honesty-block">
            <div className="rp-honesty-k">未完成 / 降级的方法</div>
            {r.downgraded_methods.map((d) => (
              <p key={d.method}>
                <span className="ws-method">{d.method}</span> — {d.reason}
              </p>
            ))}
          </div>
          <div className="rp-honesty-block">
            <div className="rp-honesty-k">本次分析的局限</div>
            <RichText text={r.limitations} />
          </div>
        </section>

        {/* ———— 评测区（外部观点对照）———— */}
        <section id="rp-eval" className="cc-card rp-domain rp-eval">
          <div className="cc-eyebrow">EVALUATION · 外部观点对照</div>
          <div className="rp-domain-title cc-serif">外部观点对照</div>
          <div className="dim" style={{ marginBottom: 16 }}>
            把市场上已有的分析观点贴进来（3-5 条），系统会对照我们的结论，告诉你：哪些已被覆盖、哪些存在冲突、哪些是我们独有的发现。
          </div>

          <div className="rp-claims-form">
            {claims.map((c, i) => (
              <div key={i} className="cc-inset rp-claim">
                <span className="cc-eyebrow">观点 {String(i + 1).padStart(2, '0')}</span>
                <Input
                  value={c.论断}
                  placeholder="观点/论断"
                  onChange={(e) => setClaims(claims.map((x, j) => (j === i ? { ...x, 论断: e.target.value } : x)))}
                />
                <Input
                  value={c.来源}
                  placeholder="来源"
                  onChange={(e) => setClaims(claims.map((x, j) => (j === i ? { ...x, 来源: e.target.value } : x)))}
                />
              </div>
            ))}
            <Button type="primary" loading={submitClaims.isPending} onClick={() => submitClaims.mutate()}>
              开始对照评测
            </Button>
          </div>

          {(evaluation.data?.evaluation.length ?? 0) > 0 && (
            <div className="rp-eval-result">
              {(evaluation.data?.evaluation ?? []).map((e) => (
                <div key={e.claim_id} className="rp-eval-row">
                  <span className={`rp-eval-badge is-${e.对照档}`}>
                    {e.对照档 === 'covered' ? '已覆盖' : e.对照档 === 'conflict' ? '有冲突' : '独有发现 ★'}
                  </span>
                  <span>{e.detail}</span>
                </div>
              ))}
            </div>
          )}

          {/* 冲突档裁决卡（裁决留痕=判例素材） */}
          {(evaluation.data?.pending_verdicts ?? []).map((p) => (
            <div key={p.cid} className="cc-inset rp-claim-verdict">
              <div className="cc-eyebrow">有冲突 · 待你裁决</div>
              <div className="rp-claim-vs">
                <div>
                  <div className="dim">我们的结论</div>
                  <div>{p.mine}</div>
                </div>
                <div>
                  <div className="dim">外部观点</div>
                  <div>{p.theirs}</div>
                </div>
              </div>
              <div className="dim">{p.detail}</div>
              <div className="rp-qc-actions">
                <Button size="small" loading={claimVerdict.isPending} onClick={() => claimVerdict.mutate({ cid: p.cid, verdict: '我方正确' })}>
                  我方正确
                </Button>
                <Button size="small" ghost onClick={() => claimVerdict.mutate({ cid: p.cid, verdict: '外部正确' })}>
                  外部正确
                </Button>
              </div>
            </div>
          ))}

          {(evaluation.data?.verdicts.length ?? 0) > 0 && (
            <div className="rp-eval-verdicts dim">
              已裁决：{evaluation.data!.verdicts.map((v) => `${v.cid} → ${v.verdict}`).join(' · ')}
            </div>
          )}
        </section>
      </div>

      {/* ———— 质检 Drawer（人工裁决）———— */}
      <Drawer open={qcDrawer} onClose={() => setQcDrawer(false)} width={460} title={<span className="cc-serif">数字质检详情 · 人工裁决</span>}>
        <div className="dim" style={{ marginBottom: 16 }}>
          系统自动复核了报告中所有承重数字。以下条目需要你判断——你的裁决会记录存档，修正后可重新装配报告。
        </div>
        {r.qc.map((q) => (
          <div key={q.id} className={`cc-inset rp-qc-item is-${q.verdict}`}>
            <div className="rp-qc-head">
              <span className="ws-method">{q.number}</span>
              <span style={{ color: VERDICT_COLOR[q.verdict] }}>
                {VERDICT_TEXT[q.verdict]}{q.issue_type ? ` · ${q.issue_type}` : ''}
              </span>
            </div>
            <div className="rp-qc-reason">{q.reason}</div>
            <div className="dim">依据：{q.basis}</div>
            {q.verdict !== 'pass' && (
              <div className="rp-qc-actions">
                {q.owner_verdict ? (
                  <Tag style={{ color: 'var(--ready)', borderColor: 'transparent', background: 'color-mix(in srgb, var(--ready) 14%, transparent)' }}>
                    已裁决：{q.owner_verdict}
                  </Tag>
                ) : (
                  <>
                    <Button
                      size="small"
                      loading={qcVerdict.isPending && qcVerdict.variables?.qid === q.id}
                      onClick={() => qcVerdict.mutate({ qid: q.id, verdict: '维持' })}
                    >
                      维持
                    </Button>
                    <Button
                      size="small"
                      ghost
                      onClick={() => qcVerdict.mutate({ qid: q.id, verdict: '修正' })}
                    >
                      修正
                    </Button>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
      </Drawer>
    </div>
  );
}
