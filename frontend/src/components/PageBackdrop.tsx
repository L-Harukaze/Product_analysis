/**
 * 全站背景动效层（Owner 需求 2026-09-16）：星野闪烁 + 萤火虫漂移 + 流星。
 * fixed + z-index:-1——画在 body 深色底之上、一切内容之下：
 * 只在页面容器的透明间隙可见，卡片/表格等实底内容自动遮挡，无需逐页调层级。
 * 纪律：纯 CSS transform/opacity 动画（GPU 合成）；固定种子伪随机（坐标渲染间稳定）；
 * pointer-events 穿透 + aria-hidden；prefers-reduced-motion 下全部静止（见 app.css）。
 * P0 首页的天体（土星/冷月）不在此层，见 HomeBackdrop。
 */

/** 固定种子伪随机（LCG） */
function seeded(seed: number): () => number {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

const rand = seeded(20260916);

interface Star {
  x: number;
  y: number;
  size: number;
  tone: 'pale' | 'blue';
  duration: number;
  delay: number;
}

const STARS: Star[] = Array.from({ length: 72 }, () => ({
  x: rand() * 100,
  y: rand() * 100,
  size: rand() > 0.86 ? 2 : 1,
  tone: rand() > 0.78 ? 'blue' : 'pale',
  duration: 2.8 + rand() * 5.5,
  delay: rand() * 7,
}));

interface Firefly {
  x: number;
  y: number;
  variant: number; // 漂移路径变体 hb-drift-1..6
  duration: number;
  delay: number;
  glowDuration: number;
}

/** 萤火虫基点手工分布（避免随机聚堆），负 delay 错相启动 */
const FIREFLIES: Firefly[] = [
  { x: 12, y: 30, variant: 1, duration: 34, delay: 0, glowDuration: 4.2 },
  { x: 78, y: 22, variant: 2, duration: 41, delay: -9, glowDuration: 5.1 },
  { x: 30, y: 70, variant: 3, duration: 37, delay: -16, glowDuration: 3.8 },
  { x: 88, y: 62, variant: 4, duration: 45, delay: -5, glowDuration: 4.8 },
  { x: 55, y: 48, variant: 5, duration: 39, delay: -22, glowDuration: 5.6 },
  { x: 8, y: 84, variant: 6, duration: 43, delay: -12, glowDuration: 4.5 },
];

/** 流星：4 颗、约 8s 周期，位置/delay/时长三者错开避免机械同步感 */
const METEORS = [
  { x: 70, y: 8, delay: 0.5, duration: 8 },
  { x: 26, y: 3, delay: 2.4, duration: 8.4 },
  { x: 88, y: 30, delay: 4.2, duration: 7.7 },
  { x: 12, y: 14, delay: 6.1, duration: 8.2 },
];

export default function PageBackdrop() {
  return (
    <div className="hbf" aria-hidden>
      {/* 星野 */}
      <div className="hb-stars">
        {STARS.map((s, i) => (
          <span
            key={i}
            className={`hb-star is-${s.tone}`}
            style={{
              left: `${s.x}%`,
              top: `${s.y}%`,
              width: s.size,
              height: s.size,
              animationDuration: `${s.duration}s`,
              animationDelay: `${s.delay}s`,
            }}
          />
        ))}
      </div>
      {/* 萤火虫：外层漂移路径（transform）× 内层呼吸光晕（opacity） */}
      {FIREFLIES.map((f, i) => (
        <span
          key={`ff-${i}`}
          className={`hb-firefly hb-drift-${f.variant}`}
          style={{
            left: `${f.x}%`,
            top: `${f.y}%`,
            animationDuration: `${f.duration}s`,
            animationDelay: `${f.delay}s`,
          }}
        >
          <span
            className="hb-firefly-core"
            style={{ animationDuration: `${f.glowDuration}s`, animationDelay: `${-i * 1.4}s` }}
          />
        </span>
      ))}
      {/* 流星：4 颗，~8s 周期错相划过 */}
      {METEORS.map((m, i) => (
        <span
          key={`mt-${i}`}
          className="hb-meteor"
          style={{
            left: `${m.x}%`,
            top: `${m.y}%`,
            animationDelay: `${m.delay}s`,
            animationDuration: `${m.duration}s`,
          }}
        />
      ))}
    </div>
  );
}
