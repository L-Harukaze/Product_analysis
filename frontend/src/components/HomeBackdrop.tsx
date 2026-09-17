/**
 * P0 首页专属天体层（Owner 需求 2026-09-16）：土星 + 冷月。
 * 星野/萤火虫/流星已抽至 PageBackdrop（全站共享，fixed 层）。
 * .hb-orbits 容器 absolute 于 hero + overflow hidden——天体溢出部分被画布裁切。
 * 纪律同 PageBackdrop：纯 CSS 动画、pointer-events 穿透、reduced-motion 静止。
 */

import type { CSSProperties } from 'react';
import PageBackdrop from './PageBackdrop';

export default function HomeBackdrop() {
  return (
    <>
      <PageBackdrop />
      <div className="hb-orbits" aria-hidden>
        {/* 土星（左侧，部分溢出）：球体+行星环（::after 前弧横过球前、::before 整环垫在球后），
            环缓慢进动摇摆（±5°）+ 球体微光呼吸 */}
        <span className="hb-saturn" style={{ left: -110, top: '56%', width: 230, height: 230 }} />
        {/* 冷月：右下角部分溢出。月面（受光+月海斑）在 ::before 上以 var(--spin) 缓转——
            斑转而光不转，观感是"月亮在自转" */}
        <span
          className="hb-moon is-cold"
          style={{ right: -70, bottom: -80, width: 220, height: 220, '--spin': '30s' } as CSSProperties}
        />
      </div>
    </>
  );
}
