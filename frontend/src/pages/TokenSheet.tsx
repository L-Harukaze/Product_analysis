/**
 * Token 试色页 v2（/__tokens，dev-only 评审物，FRONTEND.md §3.6）。
 * v1.2 深色低饱和体系 + 组件质感规范（描边微光卡 / 内嵌说明框 / 按钮阴影 /
 * 衬线标题 / 中英结合 eyebrow）。Owner 过目确认后才开始页面施工。
 * 文案均为产品真实场景。
 */

import { Alert, Button, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CopyOutlined, SearchOutlined } from '@ant-design/icons';
import EChart from '../components/EChart';
import StatusTag from '../components/StatusTag';
import './TokenSheet.css';

/* ————— ECharts 示例：D1 市场结构 · 份额堆叠 ————— */
const shareOption = {
  title: { text: 'D1 市场结构 · 份额堆叠（%）', left: 0, textStyle: { fontSize: 13 } },
  tooltip: { trigger: 'axis' as const },
  legend: { bottom: 0 },
  grid: { left: 40, right: 16, top: 44, bottom: 56 },
  xAxis: { type: 'category' as const, data: ['2021', '2022', '2023', '2024', '2025'] },
  yAxis: { type: 'value' as const, max: 100 },
  series: [
    { name: '厂商A', type: 'bar' as const, stack: 'share', data: [22, 23, 24, 25, 26] },
    { name: '厂商B', type: 'bar' as const, stack: 'share', data: [18, 17, 17, 16, 15] },
    { name: '厂商C', type: 'bar' as const, stack: 'share', data: [13, 14, 14, 15, 15] },
    { name: '厂商D', type: 'bar' as const, stack: 'share', data: [10, 10, 11, 11, 12] },
    { name: '其他', type: 'bar' as const, stack: 'share', data: [37, 36, 34, 33, 32] },
  ],
};

/* ————— ECharts 示例：竞品价格带 · 分组柱（断链降级变体） ————— */
const priceOption = {
  title: { text: '竞品价格带 · 分组柱（断链降级变体）', left: 0, textStyle: { fontSize: 13 } },
  tooltip: { trigger: 'axis' as const },
  legend: { bottom: 0 },
  grid: { left: 48, right: 16, top: 44, bottom: 56 },
  xAxis: { type: 'category' as const, data: ['红米 K80', 'iQOO Neo10', '一加 Ace5', '真我 GT7'] },
  yAxis: { type: 'value' as const, name: '元' },
  series: [
    { name: '起售价', type: 'bar' as const, data: [1999, 1899, 2099, 2199] },
    { name: '顶配价', type: 'bar' as const, data: [3299, 3499, 3599, 3699] },
  ],
};

/* ————— 质感卡片示例（产品真实场景，规范=§3.7） ————— */
const specCards = [
  {
    eyebrow: 'FINGERPRINT',
    title: '指纹 F3 · 差异化',
    body: 'L3 带证据仲裁：注入品类基线锚点与历史先例，判定、理由、置信全留痕——带着证据做最后一段判断。',
    inset: 'F3: strong · conf 0.82 · 先例 [K80, SU7]',
  },
  {
    eyebrow: 'ROUTING',
    title: '激活矩阵',
    body: '七问域为骨架、方法为填充、指纹为选择器。不适用域显式登记原因，绝不静默缺席。',
    inset: 'D7 周期相位 → S4 未触发 · 显式登记',
  },
  {
    eyebrow: 'EXECUTION',
    title: '受控执行',
    body: '方法间并发（Semaphore 8）、方法内分轮串行。五层配方组装，中间表全落盘，方法失败不传染。',
    inset: 'M03 版本阶梯 · R2/3 · 600s 上限',
  },
  {
    eyebrow: 'QC · L3',
    title: '语义质检',
    body: '承重数字必检、五类枚举封闭、逐条全量输出。QC 只质疑不裁决，最终裁决权归 Owner。',
    inset: 'K08：语义给 QC，裁决归人',
  },
];

/* ————— 最近诊断示例行（P0 下拉面板的真实形态） ————— */
interface RecentRow {
  key: string;
  product: string;
  category: string;
  status: string;
  hint: string;
  updated: string;
}

const recentRows: RecentRow[] = [
  { key: '1', product: '红米 K80', category: '手机', status: 'executing', hint: 'M03 · R2/3 执行中', updated: '2 分钟前' },
  { key: '2', product: '小米 SU7', category: '汽车', status: 'done', hint: '报告已生成', updated: '3 天前' },
  { key: '3', product: '三只松鼠', category: '零食', status: 'ready', hint: '档案齐 · 待触发执行', updated: '1 小时前' },
  { key: '4', product: 'iPhone 17', category: '手机', status: 'failed_at(routing)', hint: '仲裁超时 · 待补裁决 2 项', updated: '昨天' },
];

const recentCols: ColumnsType<RecentRow> = [
  { title: '产品', dataIndex: 'product', render: (v: string, r: RecentRow) => (<><b>{v}</b><span className="ts-dim"> · {r.category}</span></>) },
  { title: '状态', dataIndex: 'status', width: 170, render: (v: string) => <StatusTag status={v} loading={v === 'executing'} /> },
  { title: '阶段提示', dataIndex: 'hint' },
  { title: '更新', dataIndex: 'updated', width: 100 },
];

/* ————— 间距标尺 ————— */
const SPACES = ['--space-1', '--space-2', '--space-3', '--space-4', '--space-5', '--space-6', '--space-7'] as const;
const SPACE_LABELS = ['4px', '8px', '12px', '16px', '24px', '32px', '48px'] as const;

/* ————— 图表五色 ————— */
const CHART_COLORS = [
  { name: '挼蓝 #6E9BC5', css: 'var(--primary)' },
  { name: '苍翠 #519a73', css: '#519a73' },
  { name: '昏黄 #C89B40', css: '#C89B40' },
  { name: '棠梨 #B15A43', css: '#B15A43' },
  { name: '苍青 #7397ab', css: '#7397ab' },
];

const PROMPT_SNIPPET = `# 数据采集任务：红米 K80
（诊断任务 dx-2026-0114，品类：手机）

## 一、需要的表（共 2 张，仅缺失部分）
### 表 D：竞品价格带
| 字段 | 类型 | 说明 | 口径 | 置信要求 | 示例 |
|---|---|---|---|---|---|
| model_name | string | 竞品型号 | 同档位在售机型 | 官方/第三方 | iQOO Neo10 |
| price_min | number | 起售价(元) | 官方指导价 | 官方 | 1899 |

## 二、硬规则
1. 每条数据必须带 {来源URL | 置信档(官方/第三方/估算) | 口径}，无来源不入档`;

export default function TokenSheet() {
  return (
    <div className="ts-page">
      {/* 顶部品牌导航（仿 Owner 参考图 1：两侧结构小字） */}
      <header className="ts-topbar">
        <div className="ts-nav-left">
          <span className="ts-mark" aria-hidden />
          <span className="ts-nav-brand cc-serif">AIAC产品研判系统</span>
          <span className="cc-eyebrow">DIAGNOSIS ATLAS</span>
        </div>
        <div className="ts-nav-right">
          <span className="ts-nav-link">方法论</span>
          <span className="ts-nav-link">七问体系</span>
          <span className="ts-nav-link">评测闭环</span>
          <span className="ts-nav-link ts-nav-active">演示</span>
          <span className="ts-nav-sep">|</span>
          <span className="ts-nav-link">简</span>
        </div>
      </header>

      <div className="ts-intro">
        <span className="cc-eyebrow">TOKEN SHEET · V1.2 · DEV ONLY</span>
        <p>
          Owner 过目确认后才开始页面施工。每节右侧标注<span className="ts-review">评审要点</span>，文案均为产品真实场景。
        </p>
      </div>

      {/* 0 P0 首页氛围样张 */}
      <section className="ts-section ts-section-flush">
        <div className="ts-section-head">
          <h2 className="cc-serif">0 · P0 首页氛围样张</h2>
          <span className="ts-review">看：衬线大标题气质；两侧结构小字（顶部导航/底部 meta）的高级感是否到位</span>
        </div>
        <div className="ts-hero">
          <div className="ts-hero-nav">
            <div className="ts-nav-left">
              <span className="ts-mark" aria-hidden />
              <span className="ts-nav-brand cc-serif">AIAC产品研判系统</span>
              <span className="cc-eyebrow">DIAGNOSIS ATLAS</span>
            </div>
            <div className="ts-nav-right">
              <span className="ts-nav-link">方法论</span>
              <span className="ts-nav-link">七问体系</span>
              <span className="ts-nav-link ts-nav-active">演示</span>
              <span className="ts-nav-sep">|</span>
              <span className="ts-nav-link">简</span>
            </div>
          </div>
          <div className="ts-hero-body">
            <div className="cc-eyebrow ts-hero-kicker">SEVEN QUESTIONS · FOUR-LAYER TRACE · FULL AUDIT</div>
            <h1 className="ts-hero-title">AIAC产品研判系统</h1>
            <p className="ts-hero-sub">七问诊断 · 四层溯源 · 全留痕——把跨学科方法论，产品化成可复用、可编排、可评估的标准化分析系统。</p>
            <div className="ts-hero-search">
              <input placeholder="输入产品名，如：红米 K80" readOnly />
              <Button type="primary" icon={<SearchOutlined />}>开始诊断</Button>
            </div>
          </div>
          <div className="ts-hero-meta">
            <span className="cc-eyebrow">ECON PACKS M01–M09</span>
            <span className="cc-eyebrow">LOCAL DEMO · CHINESE COLOR TOKENS</span>
          </div>
        </div>
      </section>

      {/* 1 状态徽标 */}
      <section className="ts-section">
        <div className="ts-section-head">
          <h2 className="cc-serif">1 · 状态徽标 · 七态</h2>
          <span className="ts-review">看：深底上七态可辨性（低饱和亮字+同色派生底）；ready 暮山紫与 routed 暖金是否可辨</span>
        </div>
        <div className="ts-tags">
          <div className="ts-tag-item"><StatusTag status="created" /><span className="ts-dim">瞬时态·防御性渲染</span></div>
          <div className="ts-tag-item"><StatusTag status="routed" /><span className="ts-dim">断点1·等你补数</span></div>
          <div className="ts-tag-item"><StatusTag status="ready" /><span className="ts-dim">断点2·等你拍板</span></div>
          <div className="ts-tag-item"><StatusTag status="executing" loading /><span className="ts-dim">机器在跑</span></div>
          <div className="ts-tag-item"><StatusTag status="assembling" /><span className="ts-dim">装配中(瞬态)</span></div>
          <div className="ts-tag-item"><StatusTag status="done" /><span className="ts-dim">终态</span></div>
          <div className="ts-tag-item"><StatusTag status="failed_at(routing)" /><span className="ts-dim">带 stage 形态</span></div>
          <div className="ts-tag-item"><StatusTag status="failed_at(executing)" /><span className="ts-dim">带 stage 形态</span></div>
        </div>
      </section>

      {/* 2 组件质感 */}
      <section className="ts-section ts-section-flush">
        <div className="ts-section-head">
          <h2 className="cc-serif">2 · 组件质感规范</h2>
          <span className="ts-review">看：描边+微光是否"只有一点点"；内嵌说明框的凹进感；eyebrow 中英结合的节奏</span>
        </div>
        <div className="ts-spec-grid">
          {specCards.map((c) => (
            <div key={c.eyebrow} className="cc-card ts-spec-card">
              <div className="cc-eyebrow">{c.eyebrow}</div>
              <div className="ts-spec-title cc-serif">{c.title}</div>
              <p className="ts-spec-body">{c.body}</p>
              <div className="cc-inset ts-spec-inset">{c.inset}</div>
            </div>
          ))}
        </div>
      </section>

      {/* 3 按钮体系 */}
      <section className="ts-section">
        <div className="ts-section-head">
          <h2 className="cc-serif">3 · 按钮体系</h2>
          <span className="ts-review">看：主按钮柔光阴影的内嵌高级感；深字在挼蓝底上的可读性</span>
        </div>
        <div className="ts-row">
          <Button type="primary">触发执行</Button>
          <Button type="primary" danger>重放执行</Button>
          <Button>修数（默认）</Button>
          <Button type="text" className="ts-ghost">维持现状</Button>
          <Button type="link">查看报告 →</Button>
        </div>
      </section>

      {/* 4 反馈三态 */}
      <section className="ts-section">
        <div className="ts-section-head">
          <h2 className="cc-serif">4 · 反馈三态（Alert）</h2>
          <span className="ts-review">看：暗金=触发被拒(非故障)与红=失败的语义区分是否一眼可辨</span>
        </div>
        <Alert
          className="ts-alert"
          type="warning"
          showIcon
          message="1 条 L2 冲突待裁决（不裁决无法进入执行）"
          description="跨源碰撞 · 表B 份额 27%（第三方） vs 表C 29%（官方） · 涉及档案行 B2/C1"
          action={<Button size="small">去裁决</Button>}
        />
        <Alert
          className="ts-alert"
          type="error"
          showIcon
          message="路由失败（failed_at(routing)）"
          description="仲裁超时 15s ×1 · 待补裁决 2 项 · 保守档位已激活，可重试路由补全矩阵"
          action={<Button size="small" danger>重试路由</Button>}
        />
        <Alert
          className="ts-alert"
          type="success"
          showIcon
          message="第 1 次提交已入档"
          description="表A 销量序列 · 12 行 · 缺数清单剩余 2 张表"
        />
      </section>

      {/* 5 文字层级 */}
      <section className="ts-section">
        <div className="ts-section-head">
          <h2 className="cc-serif">5 · 文字层级</h2>
          <span className="ts-review">看：衬线标题与无衬线正文的搭配；eyebrow 等宽小字的出版物气质</span>
        </div>
        <div className="ts-type-scale">
          <div className="cc-eyebrow">SECTION LABEL · EYEBROW 11 / MONO / TRACKED</div>
          <div className="ts-type cc-serif" style={{ fontSize: 'var(--font-display)', lineHeight: 1.25 }}>display 44 · 衬线 · AIAC产品研判系统</div>
          <div className="ts-type cc-serif" style={{ fontSize: 'var(--font-h1)' }}>h1 26 · 红米 K80 · 经济学诊断报告</div>
          <div className="ts-type cc-serif" style={{ fontSize: 'var(--font-h2)' }}>h2 19 · D1 市场结构</div>
          <div className="ts-type cc-serif" style={{ fontSize: 'var(--font-h3)' }}>h3 15 · M03 版本阶梯定价</div>
          <div className="ts-type" style={{ fontSize: 'var(--font-body)' }}>body 14 · CR4 = 68%（官方口径，2025）——规模学习形成成本护城河，学习率约 8%/代。</div>
          <div className="ts-type" style={{ fontSize: 'var(--font-caption)', fontFamily: 'var(--font-mono)' }}>caption 12 · mono · 3 轮 · 41s · qwen-max · 1.8k tok</div>
        </div>
        <div className="ts-row ts-mt">
          <span style={{ color: 'var(--text-main)' }}>text-main 餘白：正文主色</span>
          <span style={{ color: 'var(--text-sub)' }}>text-sub 影青：辅助/说明</span>
          <span style={{ color: 'var(--text-disabled)' }}>text-disabled 苍色：禁用/L3 缺席</span>
          <span style={{ color: 'var(--text-faint)' }}>text-faint 墨色：eyebrow/水印</span>
        </div>
      </section>

      {/* 6 图表五色 */}
      <section className="ts-section">
        <div className="ts-section-head">
          <h2 className="cc-serif">6 · 图表五色（chartPalette）</h2>
          <span className="ts-review">看：五色深底实战观感——堆叠相邻可辨性、分组柱冷暖对比、暗金是否压得住暖赭</span>
        </div>
        <div className="ts-chart-colors">
          {CHART_COLORS.map((c) => (
            <div key={c.name} className="ts-chart-color">
              <div className="ts-chart-bar" style={{ background: c.css }} />
              <span className="ts-dim">{c.name}</span>
            </div>
          ))}
        </div>
        <div className="ts-charts">
          <EChart option={shareOption} height={280} />
          <EChart option={priceOption} height={280} />
        </div>
      </section>

      {/* 7 间距标尺 */}
      <section className="ts-section">
        <div className="ts-section-head">
          <h2 className="cc-serif">7 · 间距标尺</h2>
          <span className="ts-review">看：4-48 七档节奏——组件内取小档、组件间取大档</span>
        </div>
        <div className="ts-spaces">
          {SPACES.map((s, i) => (
            <div key={s} className="ts-space">
              <div className="ts-space-block" style={{ width: `var(${s})` }} />
              <span className="ts-dim">{SPACE_LABELS[i]}</span>
            </div>
          ))}
        </div>
      </section>

      {/* 8 表格实战 */}
      <section className="ts-section">
        <div className="ts-section-head">
          <h2 className="cc-serif">8 · 表格实战（P0 下拉面板形态）</h2>
          <span className="ts-review">看：failed 行整行淡底（danger 10% 派生）的克制度；深色表格行分隔</span>
        </div>
        <Table<RecentRow>
          size="small"
          columns={recentCols}
          dataSource={recentRows}
          pagination={false}
          rowClassName={(r) => (r.status.startsWith('failed_at') ? 'ts-row-failed' : '')}
        />
      </section>

      {/* 9 代码块 */}
      <section className="ts-section">
        <div className="ts-section-head">
          <h2 className="cc-serif">9 · 采集 Prompt 代码块</h2>
          <span className="ts-review">看：内嵌凹槽效果（cc-inset）+ 等宽字体；复制按钮位</span>
        </div>
        <div className="ts-codeblock cc-inset">
          <button className="ts-copy" type="button">
            <CopyOutlined /> 复制全文
          </button>
          <pre>{PROMPT_SNIPPET}</pre>
        </div>
      </section>

      <footer className="ts-footer">
        <p>
          修改流程：色值只改 <code>src/theme/tokens.ts</code>（语义）与
          <code>src/theme/chartPalette.ts</code>（图表）；新增语义 token 需先向 Owner
          提议（候选色从 cathycolor.css 挑选），确认后加入——FRONTEND.md §3.5。
        </p>
      </footer>
    </div>
  );
}
