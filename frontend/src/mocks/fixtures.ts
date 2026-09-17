/**
 * Mock fixtures（FRONTEND.md §7）——结构逐字对齐 ARCHITECTURE 13 章 JSON 示例。
 * 内容文案即演示素材（面试门面）：SU7=完整报告（weak/缺席/QC warn+fail/降级/冲突留痕），
 * K80=主演示线（routed→补数→409→执行→报告）。
 * Owner 微调 2026-09-16：文案全面用户语化（第一次使用的人也能看懂），
 * 数据表代号只在数据层保留，展示层经 labels.ts 翻译。
 */

import type {
  ActivationEntry,
  DomainSection,
  FingerprintItem,
  L2Conflict,
  MissingItem,
  MethodError,
  ReportResponse,
} from '../api/types';

/* ———— 指纹（判定来源标注：规则直判 / 定量查表 / AI 仲裁）———— */
export const k80Fingerprint: FingerprintItem[] = [
  { dimension: 'F1', label: '价格 × 频率', value: '中频中价', source: 'L2 定量·查表' },
  { dimension: 'F2', label: '信息属性', value: '搜索品', source: 'L1 规则' },
  {
    dimension: 'F3',
    label: '差异化',
    value: '强',
    source: 'L3 仲裁',
    detail: {
      reason: '同档位中差异化程度偏高：性能释放与屏幕规格和竞品拉开了代差，且"性能旗舰普及者"的品牌叙事为该产品独占',
      precedents: ['参照锚点：一加 Ace（强差异化代表机型）', '历史先例：K70（已判定的强差异化案例）'],
      confidence: 0.82,
    },
  },
  {
    dimension: 'F4',
    label: '生态',
    value: '强',
    source: 'L3 仲裁',
    detail: {
      reason: '米家生态锚点（可互联设备基数约 9 亿台）+ 芯片平台同源，用户迁移到其他生态的成本显著',
      precedents: ['参照锚点：小米 15（生态绑定强的代表机型）'],
      confidence: 0.78,
    },
  },
  { dimension: 'F5', label: '政策敏感', value: '低', source: 'L1 规则' },
  { dimension: 'F6', label: '供给形态', value: '实体', source: 'L1 规则' },
];

export const k80Activation: ActivationEntry[] = [
  { domain: 'D1 市场结构', method: 'M01', form: '标准', reason: '默认执行——分析市场集中度与竞争格局' },
  { domain: 'D2 定价机制', method: 'M03', form: '标准', reason: '价格档位中等 → 消费者对版本间价差敏感，适合阶梯定价分析' },
  { domain: 'D3 竞争互动', method: 'M05', form: '标准', reason: '属于搜索品（购买前可充分比价）→ 适合分析竞品价格联动效应' },
  { domain: 'D4 成本结构', method: 'M02', form: '标准', reason: '默认执行——分析规模效应与成本下降规律' },
  { domain: 'D5 用户价值', method: 'M06', form: '叠加', reason: '生态绑定强 → 在用户价值域叠加「总持有成本」视角（边界判定已留痕）' },
  { domain: 'D5 用户价值', method: 'M09', form: '叠加', reason: '生态绑定强 → 叠加「保值率与金融杠杆」视角（边界判定通过）' },
  { domain: 'D6 信息结构', method: 'M07', form: '标准', reason: '属于搜索品 → 适合分析信息如何影响购买决策' },
  { domain: 'D7 周期相位', method: null, form: '不适用', reason: '产品差异化强 → 周期相位分析不适用（系统已显式记录此判断，而非静默跳过）' },
];

/* ———— 数据清单（Owner 微调：展示全部所需数据，✓已采集 / ✗待采集）———— */
export const k80Missing: MissingItem[] = [
  { table: 'A', name: '市场结构 · 销量与份额序列', status: 'archived', rows: 6 },
  { table: 'B', name: '竞争格局 · 市场份额（第三方统计）', status: 'archived', rows: 2 },
  { table: 'C', name: '竞争格局 · 市场份额（官方上险）', status: 'archived', rows: 2 },
  { table: 'D', name: '竞争格局 · 竞品价格带', status: 'missing' },
  { table: 'E', name: '成本结构 · 累计销量序列', status: 'archived', rows: 4 },
  { table: 'F', name: '生态锁定 · 互联与独占功能', status: 'missing' },
  { table: 'G', name: '用户价值 · 残值与维修成本', status: 'archived', rows: 3 },
];

/* ———— 档案库行数据（Owner 微调新增：档案库 Drawer 展示 + 冲突行标红定位）———— */
export const k80ArchiveRows: Record<string, Record<string, unknown>[]> = {
  A: [
    { month: '2025-04', sales_wan: 38, share_pct: 7.2 },
    { month: '2025-05', sales_wan: 45, share_pct: 8.4 },
    { month: '2025-06', sales_wan: 41, share_pct: 8.0 },
    { month: '2025-07', sales_wan: 44, share_pct: 8.3 },
    { month: '2025-08', sales_wan: 47, share_pct: 8.6 },
    { month: '2025-09', sales_wan: 43, share_pct: 8.1 },
  ],
  B: [
    { period: '2025Q2', market_share: 26.2, source: '第三方季度出货' },
    { period: '2025Q3', market_share: 27.0, source: '第三方季度出货' }, // ← 冲突行 2
  ],
  C: [
    { period: '2025Q3', market_share: 29.0, source: '官方上险' }, // ← 冲突行 1
    { period: '2025Q2', market_share: 28.1, source: '官方上险' },
  ],
  E: [
    { quarter: '2024Q3', cum_sales_wan: 620 },
    { quarter: '2024Q4', cum_sales_wan: 810 },
    { quarter: '2025Q1', cum_sales_wan: 990 },
    { quarter: '2025Q2', cum_sales_wan: 1180 },
  ],
  G: [
    { item: '一年期残值率', value: 78, unit: '%' },
    { item: '三年维修均费', value: 412, unit: '元' },
    { item: '年均能耗成本', value: 18, unit: '元' },
  ],
};

/* ———— 采集 prompt（6.1 骨架；背景信息注入帮取数 AI 对齐）———— */
export function buildPrompt(product: string, id: string, rejection?: string, background?: string): string {
  return `# 数据采集任务：${product}
（诊断任务 ${id}，品类：手机）
${background ? `\n## 零、已知产品背景（用户提供，采数时优先对齐）\n${background}\n` : ''}
## 一、需要的表（共 2 张，仅缺失部分）
### 表 D：竞品价格带
| 字段 | 类型 | 说明 | 口径 | 置信要求 | 示例 |
|---|---|---|---|---|---|
| model_name | string | 竞品型号 | 同档位在售机型 | 官方/第三方 | iQOO Neo10 |
| price_min | number | 起售价(元) | 官方指导价 | 官方 | 1899 |
| price_max | number | 顶配价(元) | 官方指导价 | 官方 | 3499 |
| market_share | number | 份额(%) | 第三方季度出货口径 | 第三方 | 5.2 |
| source_url | string | 来源链接 | 必填 | — | https://… |

### 表 F：生态锁定量
| 字段 | 类型 | 说明 | 口径 | 置信要求 | 示例 |
|---|---|---|---|---|---|
| model_name | string | 机型 | 同表 D | 官方/第三方 | iQOO Neo10 |
| iot_linkable | number | 可互联设备数 | 米家认证口径 | 第三方 | 3200 |
| eco_exclusive | number | 生态独占功能数 | 厂商口径 | 第三方 | 4 |
| source_url | string | 来源链接 | 必填 | — | https://… |

## 二、硬规则
1. 每条数据必须带 {来源URL | 置信档(官方/第三方/估算) | 口径}，无来源不入档
2. 总量数字以官方值为档案基准，第三方口径单独标注，不可混用
3. 断链序列禁止插值；跨产品对比必须同期取样
4. 估算值必须显式标注"估算"
5. 时间范围：2024-01 至 2025-12（路由决定）

## 三、输出格式
严格按以下 JSON 结构返回（与 input.schema 一致）：
{"tables": {"D": [{"model_name": "…", "price_min": 1899, "price_max": 3499, "market_share": 5.2, "source_url": "https://…"}],
             "F": [{"model_name": "…", "iot_linkable": 3200, "eco_exclusive": 4, "source_url": "https://…"}]}}

## 四、打回条款
${rejection ?? '上次提交的拒绝原因（如有）：无——首次生成。'}`;
}

/* ———— L2 冲突（缺数清空自动出现，演示"触发被拒→裁决→放行"闭环）———— */
export const k80Conflict: L2Conflict = {
  id: 'CON-01',
  invariant: '同一指标、不同来源数据不一致',
  detail:
    '「2025Q3 市场份额」两个来源给出的数值不同：27%（第三方统计口径） vs 29%（官方上险口径）——需要你决定采信哪个，或直接修正数据',
  rows: ['表B 行 2', '表C 行 1'],
};

/* ———— 执行计划（方法间并发、方法内串行分轮；M02 失败演示"失败不传染+重试/跳过"）———— */
export interface ExecMethodPlan {
  method: string;
  rounds: number;
  staggerMs: number;
  roundMs: number;
  failAfterRounds?: number; // 达到该轮后 failed
  error?: MethodError;
}
export const k80ExecPlan: ExecMethodPlan[] = [
  { method: 'M01', rounds: 3, staggerMs: 0, roundMs: 2000 },
  {
    method: 'M02',
    rounds: 3,
    staggerMs: 300,
    roundMs: 2000,
    failAfterRounds: 2,
    error: {
      timeout: '600 秒（该方法设定的上限）',
      retries: 2,
      split_record: '已自动拆分轮次重跑 1 次，仍然超时',
      raw: 'LLMExecutorTimeout: round R2b exceeded time_limit=600s (qwen-max)',
    },
  },
  { method: 'M03', rounds: 4, staggerMs: 600, roundMs: 2000 },
  { method: 'M05', rounds: 3, staggerMs: 900, roundMs: 2000 },
  { method: 'M06', rounds: 3, staggerMs: 1200, roundMs: 2000 },
  { method: 'M07', rounds: 3, staggerMs: 1500, roundMs: 2000 },
  { method: 'M09', rounds: 4, staggerMs: 1800, roundMs: 2000 },
];
export const ASSEMBLING_MS = 2200;

/* ———— K80 报告（执行 done 后挂载；Owner 微调：内容加长 + \n\n 分段）———— */
const k80Domains: DomainSection[] = [
  {
    domain_id: 'D1',
    title: 'D1 市场结构',
    status: 'active',
    items: [
      {
        L1_fact:
          '2025 年第三季度，中国 2000-2500 元档智能手机市场 CR4（前四名合计份额）为 68%，数据来自官方出货量统计。\n\n该档位是安卓阵营出货量最大的价格带，头部四家厂商合计占据约七成份额，市场集中度处于高位。',
        L2_mechanism:
          '该档位存在双重护城河：规模学习效应使头部厂商的单位成本持续下降；线下渠道密度决定了终端触达能力。\n\n档位集中度的变化节奏由头部厂商的代际发布周期驱动——每次旗舰配置下放都会重塑一次份额格局。',
        L3_quantification:
          'CR4 同比提升 3.1 个百分点；新增份额的 78% 由前两名厂商瓜分。\n\n长尾厂商（第五名之后）份额从 39% 压缩至 32%，且压缩速度仍在加快。',
        L4_prescription:
          '结构性机会在档位顶部（2400-2500 元）：头部厂商在此区间布置较弱，跟随者可通过错位配置避开正面压制。\n\n新进入者若主打 2000-2200 元标准位，将直接承受头部机型的火力覆盖，不建议。',
        confounder_check: '已剔除国家补贴政策对第三季度基数的脉冲扰动（采用环比口径复核）。',
        evidence_strength: '官方',
        chart_refs: ['chart-d1-share'],
        method: 'M01',
      },
      {
        L1_fact:
          'K80 上市首月档位份额 9.2%（第三方周度激活口径推算），首周即出现渠道售罄。\n\n备货节奏成为份额爬坡的直接约束，而非终端需求不足。',
        L2_mechanism:
          '新品份额爬坡由供应链备货深度决定：首周售罄说明需求领先于供给，份额被备货量压制。\n\n这是典型的供给约束型爬坡，与需求疲软导致的份额不振有本质区别，两者的应对动作完全不同。',
        L3_quantification:
          '备货每增加 20 万台，份额爬坡期缩短约 1.5 周。\n\n按当前爬坡曲线外推，满备货状态下首月份额可达 11-12%。',
        L4_prescription:
          '份额预测的关键变量是供应链备货计划，而非营销投入。\n\n建议以供应链数据为核心变量建立份额预测模型；营销侧只需保证转化率不拖后腿。',
        confounder_check: '线上/线下渠道激活口径差异已分层统计，避免口径混算。',
        evidence_strength: '第三方',
        chart_refs: [],
        method: 'M01',
      },
    ],
  },
  {
    domain_id: 'D2',
    title: 'D2 定价机制',
    status: 'active',
    items: [
      {
        L1_fact:
          'K80 提供五个版本，官方指导价 1999 / 2299 / 2599 / 2899 / 3299 元。\n\n基线版与顶配版价差 1300 元，覆盖了该档位几乎全部主流预算点。',
        L2_mechanism:
          '版本阶梯定价的经济学逻辑：基线版锚定流量与口碑（低毛利、高声量），顶配版拉毛利与品牌心智（高毛利、低销量）。\n\n中间版本的升级率揭示了消费者的边际支付意愿——升级率出现断层的位置，就是定价失误点。',
        L3_quantification:
          '阶梯升级率：1999→2299 为 41%，2299→2599 骤降至 12%（订单结构，第三方数据）。\n\n2599 档是明显的升级断层点：消费者认为该档的配置增量不值 300 元差价。',
        L4_prescription:
          '维持整体阶梯结构不变；重点强化 2599 档的配置感知。\n\n可考虑将某项高感知配置（快充或存储规格）从 2899 档下放至 2599 档，修复断层。',
        confounder_check: '以旧换新补贴对升级率的上拉效应已剔除（补贴前后订单结构对比）。',
        evidence_strength: '第三方',
        chart_refs: ['chart-d2-ladder'],
        method: 'M03',
      },
    ],
  },
  {
    domain_id: 'D3',
    title: 'D3 竞争互动',
    status: 'active',
    items: [
      {
        L1_fact:
          'K80 开售后，同档位竞品 iQOO Neo10 单周订单量下降 7%（第三方周度预估）。\n\n该影响在 K80 首销周即出现，随 K80 备货恢复而减弱。',
        L2_mechanism:
          '搜索品市场中，直接竞品间存在显著的价格联动：消费者比价充分，一方的性价比优势会直接抽走另一方的订单。\n\n交叉价格弹性为负且显著，说明该档位已进入零和博弈区间。',
        L3_quantification:
          '交叉弹性 ε ≈ 0.6（8 周窗口回归，估算口径）——K80 每 1% 的相对性价比提升，约抽走竞品 0.6% 的订单。\n\n该弹性高于档位历史均值（0.4-0.5），说明本轮竞争烈度偏高。',
        L4_prescription:
          '竞品被动降价概率高（弹性传导使其不得不跟），建议锚定自身代际节奏，不打价格战。\n\n若竞品降价，用权益（延保、碎屏险等）对冲而非直接跟进，保住价格体系。',
        confounder_check: '竞品同期焕新发布的影响已注记（存在口径混用风险，结论置信度受限）。',
        evidence_strength: '估算',
        chart_refs: [],
        method: 'M05',
      },
    ],
  },
  {
    domain_id: 'D4',
    title: 'D4 成本结构',
    status: 'weak',
    note: '学习曲线分析未完成：执行超时（自动重试 2 次仍失败）。本域降级为弱适用——学习率未量化、原因显式登记；成本侧结论以 D1 的规模证据侧面支撑。诚实登记优于编造数字。',
  },
  {
    domain_id: 'D5',
    title: 'D5 用户价值',
    status: 'active',
    items: [
      {
        L1_fact:
          'K80 三年总持有成本（TCO，含残值/能耗/维修）约为同档竞品均值的 91%（第三方估算）。\n\n其中残值优势贡献最大：一年期保值率 78%，高于同档均值 2.1 个百分点。',
        L2_mechanism:
          'TCO 优势是用户价值的核心经济动因：消费者实际感知的是"三年总共花的钱"，而非"到手价"。\n\n生态绑定放大留存——米家互联设备基数使换机沉没成本显性化，形成事实上的锁定效应。',
        L3_quantification:
          'TCO 差额 1200 元中，残值贡献 64%；生态锁定指数 0.71（强档）。\n\n按三年周期折算，K80 每月综合持有成本比竞品均值低约 33 元。',
        L4_prescription:
          '营销应量化"三年总持有成本"对比（月均口径最直观），而非单点参数比拼。\n\n保值率与生态延续性是可承诺项，建议写入官方以旧换新政策以强化预期。',
        confounder_check: '家用充电条件对能耗成本的结构性影响已分层；样本城市以一二线为主（已注记）。',
        evidence_strength: '估算',
        chart_refs: [],
        method: 'M06 / M09',
      },
    ],
  },
  {
    domain_id: 'D6',
    title: 'D6 信息结构',
    status: 'active',
    items: [
      {
        L1_fact:
          '发布期搜索指数 1.8 亿次，首月负面口碑率 2.9%（第三方舆情口径）。\n\n负面集中在前两周的屏幕供应商争议，之后快速衰减。',
        L2_mechanism:
          '搜索品的信息结构特征：购买前消费者以参数对比为主（理性信息主导决策）；交付后转入体验品逻辑（口碑与晒单主导增量购买）。\n\n两个阶段的营销打法应完全不同——这是多数厂商混淆的地方。',
        L3_quantification:
          '负面事件衰减半衰期 9 天，快于档位均值 15 天——争议未沉淀为长期口碑负债。\n\n发布期窗口内，参数类内容的首页渗透率是情感类内容的 2.3 倍。',
        L4_prescription:
          '首销期参数对比物料的优先级应高于情感向物料；争议应对以"快速给出硬信息"为纲。\n\n交付期启动晒单激励，承接口碑二次传播。',
        confounder_check: '样本以公开社媒为主，私域口碑不可测（已登记为局限）。',
        evidence_strength: '第三方',
        chart_refs: [],
        method: 'M07',
      },
    ],
  },
  {
    domain_id: 'D7',
    title: 'D7 周期相位',
    status: 'not_applied',
    note: '产品差异化强 → 周期相位分析不适用（系统已显式记录此判断，而非静默跳过——"为什么不做"本身也是分析结论）。',
  },
];

const k80Charts: ReportResponse['charts'] = [
  {
    chart_id: 'chart-d1-share',
    type: 'bar-stack',
    note: '市场份额堆叠趋势（口径：官方出货量统计）',
    option: {
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      grid: { left: 40, right: 16, top: 32, bottom: 56 },
      xAxis: { type: 'category', data: ['2023', '2024', '2025Q3'] },
      yAxis: { type: 'value', max: 100 },
      series: [
        { name: '厂商A', type: 'bar', stack: 's', data: [19, 21, 24] },
        { name: '厂商B', type: 'bar', stack: 's', data: [17, 17, 18] },
        { name: '厂商C', type: 'bar', stack: 's', data: [14, 15, 15] },
        { name: '厂商D', type: 'bar', stack: 's', data: [11, 11, 11] },
        { name: '其他', type: 'bar', stack: 's', data: [39, 36, 32] },
      ],
    },
  },
  {
    chart_id: 'chart-d2-ladder',
    type: 'bar-group',
    note: '版本价格阶梯对比（官方指导价；数据点不连续，不做趋势插值）',
    option: {
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      grid: { left: 48, right: 16, top: 32, bottom: 56 },
      xAxis: { type: 'category', data: ['K80', 'Neo10', 'Ace5', 'GT7'] },
      yAxis: { type: 'value', name: '元' },
      series: [
        { name: '起售价', type: 'bar', data: [1999, 1899, 2099, 2199] },
        { name: '顶配价', type: 'bar', data: [3299, 2899, 3499, 3299] },
      ],
    },
  },
];

export const k80Report: ReportResponse = {
  domains: k80Domains,
  qc: [
    { id: 'QC-01', number: 'CR4 = 68%', verdict: 'pass', issue_type: null, reason: '与官方出货报告一致，可溯源', basis: '市场结构 · 销量与份额序列 第 2 行原始数据' },
    {
      id: 'QC-02',
      number: '阶梯升级率 41%',
      verdict: 'warn',
      issue_type: '量级存疑',
      reason: '41% 与该档位常见区间（30-50%）的上边界重合，量级合理性无法完全核验',
      basis: '竞争格局 · 竞品价格带 第 4 行订单结构记录',
    },
    {
      id: 'QC-03',
      number: '首月份额 9.2%',
      verdict: 'fail',
      issue_type: '溯源不符',
      reason: '9.2% 由周度激活口径推算月度时发生口径混算，与档案原始记录（8.1%）不符',
      basis: '竞争格局 · 市场份额（第三方统计） 第 3 行原始数据（周度口径）',
    },
    { id: 'QC-04', number: '交叉弹性 0.6', verdict: 'pass', issue_type: null, reason: '回归窗口与置信档声明完整', basis: '交叉弹性分析的中间过程记录（M05-R2）' },
  ],
  charts: k80Charts,
  conflict_log:
    '装配期冲突仲裁记录：交叉弹性分析（M05）与市场结构分析（M01）对档位份额的口径不一致 → 按证据强度规则（官方 > 第三方）仲裁 → 败方（第三方口径 9.2%）降级保留、留痕可查。本例无同强度对撞，未触发人工回交。',
  l2_conflict_notes:
    '人工裁决记录：市场份额 27%（第三方统计） vs 29%（官方上险）冲突（CON-01）→ 采信官方口径 29%，第三方口径单独标注保留（2026-09-16）。',
  downgraded_methods: [
    { method: '学习曲线分析（M02）', reason: '执行超时（自动重试 2 次仍失败）——错误已记录到系统缺陷清单，下次诊断将规避同类问题' },
  ],
  limitations:
    '学习曲线分析（M02）：学习率未量化（数据断链，按规则禁止插值补数）；金融杠杆分析（M09）：保值率序列仅 2 期，结论降置信处理；交叉弹性分析（M05）：基于估算数据，置信档=估算。',
};

/* ———— SU7（done 深度案例：报告直开 + 评测演示）———— */
export const su7Report: ReportResponse = {
  ...k80Report,
  domains: [
    k80Domains[0], // D1 active 结构复用（演示数据同构）
    k80Domains[1],
    k80Domains[2],
    { domain_id: 'D4', title: 'D4 成本结构', status: 'weak', note: '学习曲线分析未完成：执行超时（自动重试 2 次仍失败），降级弱适用；学习率未量化、原因显式登记。' },
    k80Domains[4],
    k80Domains[5],
    k80Domains[6],
  ],
};

/* ———— 演示辅助：提交示例（P1 提交区"填入示例"按钮，dev 演示用非产品功能）———— */
export const SAMPLE_OK_D = `{"tables": {"D": [
  {"model_name": "iQOO Neo10", "price_min": 1899, "price_max": 2899, "market_share": 5.2, "source_url": "https://example.com/neo10"},
  {"model_name": "一加 Ace5", "price_min": 2099, "price_max": 3499, "market_share": 4.8, "source_url": "https://example.com/ace5"},
  {"model_name": "真我 GT7", "price_min": 2199, "price_max": 3299, "market_share": 3.9, "source_url": "https://example.com/gt7"},
  {"model_name": "荣耀 GT", "price_min": 1999, "price_max": 3299, "market_share": 3.5, "source_url": "https://example.com/gt"}
]}}`;

export const SAMPLE_REJECT_D = `{"tables": {"D": [
  {"model_name": "iQOO Neo10", "price_min": 1899, "price_max": 2899, "market_share": "5.2%", "source_url": "https://example.com/neo10"},
  {"model_name": "一加 Ace5", "price_min": 2099, "price_max": 3499, "market_share": 4.8}
]}}`;

export const SAMPLE_OK_F = `{"tables": {"F": [
  {"model_name": "iQOO Neo10", "iot_linkable": 3100, "eco_exclusive": 3, "source_url": "https://example.com/neo10-eco"},
  {"model_name": "一加 Ace5", "iot_linkable": 2400, "eco_exclusive": 2, "source_url": "https://example.com/ace5-eco"},
  {"model_name": "真我 GT7", "iot_linkable": 1900, "eco_exclusive": 2, "source_url": "https://example.com/gt7-eco"}
]}}`;

/* ———— 评测 claim 示例与固定对照结果（三层对照：覆盖/冲突/增量）———— */
export const SAMPLE_CLAIMS = [
  { 论断: 'K80 是 2000 档性价比标杆', 依据: '横向配置对比', 来源: '自媒体评测', 立场: '正面' },
  { 论断: 'K80 一年期保值率低于同档均值', 依据: '二手平台报价抽样', 来源: '数码媒体', 立场: '负面' },
  { 论断: '天马屏是 K80 的减配点', 依据: '屏幕供应商拆解', 来源: '技术论坛', 立场: '负面' },
];
