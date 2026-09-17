/**
 * 状态徽标（FRONTEND.md §3.1 总表，v1.2 深色版）。
 * 枚举与契约 3.2 逐字一致；AntD Tag 禁用预设色。
 * 深色主题：低饱和亮字档 + 同色低透明底/描边（color-mix 派生，FRONTEND.md §3.4）。
 */

import { Tag } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { statusLabel } from '../labels';

const STATUS_TEXT: Record<string, string> = {
  created: 'var(--text-sub)',
  routed: 'var(--warning-text)',
  ready: 'var(--ready)',
  executing: 'var(--primary)',
  assembling: 'var(--primary)',
  done: 'var(--success)',
  failed_at: 'var(--danger)',
};

export default function StatusTag({ status, loading = false }: { status: string; loading?: boolean }) {
  const isFailed = status.startsWith('failed_at');
  const c = STATUS_TEXT[isFailed ? 'failed_at' : status] ?? STATUS_TEXT.created;

  return (
    <Tag
      style={{
        color: c,
        background: `color-mix(in srgb, ${c} 14%, transparent)`,
        borderColor: `color-mix(in srgb, ${c} 30%, transparent)`,
        marginInlineEnd: 0,
      }}
    >
      {loading && <LoadingOutlined spin style={{ marginInlineEnd: 4 }} />}
      {statusLabel(status)}
    </Tag>
  );
}
