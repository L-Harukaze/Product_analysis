/**
 * 完整分析历史（Owner 新增 2026-09-16）：右栏底部收尾卡片，宽度同提交历史，
 * 高度自动延伸至与左栏《数据清单》底部对齐（flex:1 吸收剩余空间）。
 * 内容 = 产品特征判定 + 分析方法的具体分析信息（结构化全量，可回溯）。
 */

import type { ActivationEntry, DiagnosisDetail, FingerprintItem } from '../api/types';
import { SOURCE_LABELS, methodLabel, tableLabel } from '../labels';

function FpRow({ f }: { f: FingerprintItem }) {
  return (
    <div className="ah-fp-row">
      <div className="ah-fp-head">
        <span className="ah-fp-label">{f.label}</span>
        <span className="cc-serif ah-fp-value">{f.value}</span>
        <span className="ah-fp-src">{SOURCE_LABELS[f.source] ?? f.source}</span>
      </div>
      {f.detail && <div className="ah-fp-reason dim">{f.detail.reason}</div>}
    </div>
  );
}

export default function AnalysisHistoryCard({ detail }: { detail: DiagnosisDetail }) {
  // 类型谓词而非裸 filter：否则 TS 不会收窄 `method: string | null`，
  // methodLabel(a.method) 会报 TS2345 并让 `npm run build`（tsc --noEmit && vite build）失败
  const activeMethods = (detail.activation_matrix ?? []).filter(
    (a): a is ActivationEntry & { method: string } => Boolean(a.method),
  );
  const notApplied = (detail.activation_matrix ?? []).filter((a) => !a.method);
  const tables = Array.from(new Set((detail.missing_data ?? []).map((m) => m.table)));

  return (
    <section className="cc-card ws-card ws-analysis-card">
      <div className="ws-card-head">
        <div>
          <div className="cc-eyebrow">FULL ANALYSIS TRACE</div>
          <div className="ws-card-title cc-serif">完整分析历史</div>
        </div>
        <span className="dim">从判定到方法的全部依据，可回溯</span>
      </div>

      <div className="ah-body">
        <div className="ah-section">
          <div className="ah-section-title">产品特征判定（六大维度）</div>
          <div className="ah-fp-list">
            {(detail.fingerprint ?? []).map((f) => <FpRow key={f.dimension} f={f} />)}
          </div>
        </div>

        <div className="ah-section">
          <div className="ah-section-title">分析方法（{activeMethods.length} 项 · 依据逐条可查）</div>
          <div className="ah-method-list">
            {activeMethods.map((a) => (
              <div key={`${a.domain}-${a.method}`} className="ah-method">
                <div className="ah-method-head">
                  <span className="ws-method">{methodLabel(a.method)}</span>
                  <span className="ah-method-form">{a.method} · {a.form} · {a.domain.split(' ')[0]}</span>
                </div>
                <div className="ah-method-reason">{a.reason}</div>
              </div>
            ))}
            {notApplied.map((a) => (
              <div key={a.domain} className="ah-method is-na">
                <div className="ah-method-head">
                  <span className="dim">{a.domain}</span>
                  <span className="ah-method-form">不适用</span>
                </div>
                <div className="ah-method-reason dim">{a.reason}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="ah-section">
          <div className="ah-section-title">数据基础（{tables.length} 张表 · 来源与口径逐行留痕）</div>
          <div className="ah-tables">
            {tables.map((t) => (
              <span key={t} className="ah-table-chip">{tableLabel(t)}</span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
