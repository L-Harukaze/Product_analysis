/**
 * 自封装 EChart 组件（FRONTEND.md §2）：init / ResizeObserver / dispose。
 * 主题（系列色 + 中性色）在此统一注册注入，调用方 option 零视觉属性——
 * 后端下发的 charts[].option 也不含颜色（FRONTEND.md §9 图表视觉边界约定）。
 */

import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import { chartPalette, chartNeutrals, CHART_THEME } from '../theme/chartPalette';

echarts.registerTheme(CHART_THEME, {
  color: [...chartPalette],
  textStyle: {
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', sans-serif",
    color: chartNeutrals.axisLabel,
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: chartNeutrals.axisLine } },
    axisTick: { lineStyle: { color: chartNeutrals.axisLine } },
    axisLabel: { color: chartNeutrals.axisLabel },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisLabel: { color: chartNeutrals.axisLabel },
    splitLine: { lineStyle: { color: chartNeutrals.splitLine } },
  },
  legend: { textStyle: { color: chartNeutrals.legend } },
});

interface Props {
  option: echarts.EChartsOption;
  height?: number;
}

export default function EChart({ option, height = 300 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts>();

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = echarts.init(el, CHART_THEME);
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = undefined;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option);
  }, [option]);

  return <div ref={containerRef} style={{ height, width: '100%' }} />;
}
