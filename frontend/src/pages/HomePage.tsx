/**
 * P0 首页（FRONTEND.md §5）——仪式感 + 唯一列表入口。
 * hero（两侧结构小字）+ 大搜索 + staged 等待动画 + 下拉式最近诊断面板。
 * 提交 = POST /diagnoses 同步事务 A（P-5 ≤15s），等待期为前端 staged 动画（无实时 trace，契约无中途端点）。
 */

import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Collapse, Form, Input, Popconfirm, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DeleteOutlined, DownOutlined, SearchOutlined } from '@ant-design/icons';
import { api } from '../api/diagnoses';
import type { CreateDiagnosisRequest, DiagnosisSummary } from '../api/types';
import StatusTag from '../components/StatusTag';
import HomeBackdrop from '../components/HomeBackdrop';

const STAGE_LABELS = ['解析产品与品类', '判断产品特征（六大维度）', '深度比对同类产品（AI 仲裁）', '确定分析方法与所需数据'];
const STAGE_MS = 900;
const STAGED_TOTAL = STAGE_LABELS.length * STAGE_MS;

type FilterKey = 'all' | 'routed' | 'ready' | 'executing' | 'done' | 'failed';
const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'routed', label: '待补数据' },
  { key: 'ready', label: '待执行' },
  { key: 'executing', label: '执行中' },
  { key: 'done', label: '已完成' },
  { key: 'failed', label: '失败' },
];

function matchFilter(s: DiagnosisSummary, f: FilterKey): boolean {
  if (f === 'all') return true;
  if (f === 'failed') return s.status.startsWith('failed_at');
  if (f === 'executing') return s.status === 'executing' || s.status === 'assembling';
  return s.status === f;
}

export default function HomePage() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [form] = Form.useForm();
  const [panelOpen, setPanelOpen] = useState(false);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [stage, setStage] = useState<number>(-1); // -1 未提交；0-3 动画步；4 完成
  const startedAt = useRef(0);

  const list = useQuery({ queryKey: ['dx-list'], queryFn: () => api.listDiagnoses() });
  const reroute = useMutation({
    mutationFn: (id: string) => api.reroute(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dx-list'] }),
  });
  const del = useMutation({
    mutationFn: (id: string) => api.deleteDiagnosis(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dx-list'] }),
  });

  const create = useMutation({
    mutationFn: (req: CreateDiagnosisRequest) => api.createDiagnosis(req),
    onSuccess: (res) => {
      setStage(STAGE_LABELS.length);
      const wait = Math.max(0, STAGED_TOTAL - (Date.now() - startedAt.current));
      setTimeout(() => nav(`/workspace/${res.diagnosis_id}`), wait + 400);
      void qc.invalidateQueries({ queryKey: ['dx-list'] });
    },
    onError: () => setStage(-1),
  });

  const submit = (v: { product_name: string; category_hint?: string; price?: number; background?: string }) => {
    startedAt.current = Date.now();
    setStage(0);
    STAGE_LABELS.forEach((_, i) => setTimeout(() => setStage(i), i * STAGE_MS));
    create.mutate({
      product_name: v.product_name,
      category_hint: v.category_hint || undefined,
      known_facts: v.price ? { price: v.price } : undefined,
      background: v.background || undefined,
    });
  };

  const rows = (list.data ?? []).filter((r) => matchFilter(r, filter));
  const counts = (f: FilterKey) => (list.data ?? []).filter((r) => matchFilter(r, f)).length;

  const cols: ColumnsType<DiagnosisSummary> = [
    {
      title: '产品',
      dataIndex: 'product_name',
      render: (v: string, r: DiagnosisSummary) => (
        <>
          <b>{v}</b>
          <span className="dim"> · {r.category}</span>
        </>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 180,
      render: (v: string) => <StatusTag status={v} loading={v === 'executing'} />,
    },
    { title: '阶段提示', dataIndex: 'stage_hint', render: (v: string, r: DiagnosisSummary) => (
      <>
        {v}
        {r.pending_conflicts_n > 0 && <span className="warn-inline"> · {r.pending_conflicts_n} 处数据冲突待处理</span>}
      </>
    ) },
    { title: '更新', dataIndex: 'updated_at', width: 110, render: (v: string) => new Date(v).toLocaleDateString('zh-CN') },
    {
      title: '操作',
      width: 170,
      render: (_: unknown, r: DiagnosisSummary) => (
        // 外层 span 拦截行点击冒泡：整行可进工作台，但操作按钮不应触发跳转
        <span onClick={(e) => e.stopPropagation()}>
          {r.status === 'failed_at(routing)' ? (
            <Button
              size="small"
              danger
              loading={reroute.isPending && reroute.variables === r.diagnosis_id}
              onClick={() => reroute.mutate(r.diagnosis_id)}
            >
              重试路由
            </Button>
          ) : (
            <span className="dim">进入 →</span>
          )}
          <Popconfirm
            title="删除这条诊断？"
            description="仅删除诊断记录与提交历史，产品档案与已采集数据保留。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => del.mutate(r.diagnosis_id)}
          >
            <Button
              size="small"
              type="text"
              danger
              aria-label="删除"
              icon={<DeleteOutlined />}
              loading={del.isPending && del.variables === r.diagnosis_id}
            />
          </Popconfirm>
        </span>
      ),
    },
  ];

  const submitting = stage >= 0;

  return (
    <div className="home">
      <div className="home-hero">
        <HomeBackdrop />
        <div className="home-nav">
          <div className="nav-left">
            <span className="mark" aria-hidden />
            <span className="nav-brand cc-serif">AIAC产品研判系统</span>
            <span className="cc-eyebrow">DIAGNOSIS ATLAS</span>
          </div>
          <div className="nav-right">
            <span className="nav-link">方法论</span>
            <span className="nav-link">七问体系</span>
            <span className="nav-link ts-nav-active">演示</span>
            <span className="nav-sep">|</span>
            <span className="nav-link">简</span>
          </div>
        </div>

        <div className="home-body">
          <div className="cc-eyebrow home-kicker">SEVEN QUESTIONS · FOUR-LAYER TRACE · FULL AUDIT</div>
          <h1 className="home-title cc-serif">AIAC产品研判系统</h1>
          <p className="home-sub">七问诊断 · 四层溯源 · 全留痕——把跨学科方法论产品化成可复用、可编排、可评估的标准化分析系统</p>

          {!submitting ? (
            <Form form={form} layout="vertical" className="home-form" onFinish={submit}>
              <Form.Item name="product_name" noStyle rules={[{ required: true, message: '请输入产品名' }]}>
                <Input size="large" placeholder="输入产品名，如：红米 K80" className="home-input" autoComplete="off" />
              </Form.Item>
              <Button type="primary" size="large" htmlType="submit" icon={<SearchOutlined />} className="home-submit-btn">
                开始诊断
              </Button>
              <Collapse
                ghost
                className="home-advanced"
                items={[{
                  key: 'adv',
                  label: <span className="dim">高级选项（可选）</span>,
                  children: (
                    <div className="home-advanced-body">
                      <Form.Item
                        name="background"
                        label="产品背景信息"
                        className="home-fi home-fi-wide"
                        extra={<span className="dim">把你知道的产品信息直接贴进来（定位、参数、竞品、定价策略…）——信息越完整，系统对产品的理解和后续分析就越准，也会同步给取数环节参考。不填则完全由 AI 自行判断。</span>}
                      >
                        <Input.TextArea
                          autoSize={{ minRows: 4, maxRows: 10 }}
                          autoComplete="off"
                          placeholder={'示例：红米 K80，2025 年底发布的中端性能旗舰，首发价 1999 元起。\n主打骁龙 8s Gen4 + 2K 直屏，直接竞品为 iQOO Neo10、一加 Ace5。\n米家生态深度互联，目标人群为预算敏感的性能向用户。'}
                        />
                      </Form.Item>
                      <Form.Item
                        name="category_hint"
                        label="品类提示"
                        className="home-fi"
                        extra={<span className="dim">告诉系统这个产品属于什么品类（如：手机、零食、汽车）。不填则由 AI 自动判断</span>}
                      >
                        <Input placeholder="手机（缺省自动判断）" autoComplete="off" />
                      </Form.Item>
                      <Form.Item
                        name="price"
                        label="已知事实 · 首发价"
                        className="home-fi"
                        extra={<span className="dim">已知价格可以帮助系统更准确地判断价格档位（可选）</span>}
                      >
                        <Input type="number" placeholder="1999" autoComplete="off" />
                      </Form.Item>
                    </div>
                  ),
                }]}
              />
            </Form>
          ) : (
            <div className="home-staged cc-card">
              <div className="cc-eyebrow">ROUTING IN PROGRESS · 事务 A</div>
              <div className="home-staged-list">
                {STAGE_LABELS.map((label, i) => (
                  <div key={label} className={`home-staged-item ${stage > i ? 'is-done' : ''} ${stage === i ? 'is-current' : ''}`}>
                    <span className="staged-dot">{stage > i ? '✓' : i + 1}</span>
                    <span>{label}</span>
                    {stage === i && <span className="staged-spin" />}
                  </div>
                ))}
              </div>
              {create.isError && <div className="home-staged-error">创建失败：{(create.error as Error)?.message ?? '请重试'}</div>}
              {stage >= STAGE_LABELS.length && !create.isError && <div className="home-staged-ok">就绪 · 正在进入数据工作台…</div>}
            </div>
          )}
        </div>

        <div className="home-meta">
          <span className="cc-eyebrow">经济学方法论 · 七大分析包</span>
          <span className="cc-eyebrow">LOCAL DEMO · CHINESE COLOR TOKENS</span>
        </div>
      </div>

      {/* 下拉式最近诊断 */}
      <div className="home-panel">
        <button type="button" className="home-panel-toggle" onClick={() => setPanelOpen((v) => !v)}>
          <DownOutlined rotate={panelOpen ? 180 : 0} />
          <span className="cc-serif" style={{ fontSize: 'var(--font-h3)' }}>最近诊断</span>
          <span className="dim">{list.data?.length ?? 0} 条 · 点击{panelOpen ? '收起' : '展开'}</span>
        </button>
        {panelOpen && (
          <div className="cc-card home-panel-body">
            <div className="home-filters">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  className={`home-filter ${filter === f.key ? 'is-active' : ''}`}
                  onClick={() => setFilter(f.key)}
                >
                  {f.label} {counts(f.key)}
                </button>
              ))}
            </div>
            <Table<DiagnosisSummary>
              size="small"
              columns={cols}
              dataSource={rows}
              rowKey="diagnosis_id"
              pagination={false}
              loading={list.isLoading}
              rowClassName={(r) => (r.status.startsWith('failed_at') ? 'row-failed' : '')}
              onRow={(r) => ({ onClick: () => nav(`/workspace/${r.diagnosis_id}`), style: { cursor: 'pointer' } })}
            />
          </div>
        )}
      </div>
    </div>
  );
}
