import { useEffect, useRef } from "react";

// MetricChart 动态加载 ECharts，避免首屏把图表库打进主 bundle。
type MetricChartProps = {
  title: string;
  labels: string[];
  values: number[];
};

export function MetricChart({ title, labels, values }: MetricChartProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let disposed = false;
    let chart: {
      dispose: () => void;
      setOption: (option: unknown) => void;
    } | null = null;
    void import("echarts").then((echarts) => {
      if (!ref.current || disposed) return;
      chart = echarts.init(ref.current);
      chart.setOption({
        title: { text: title, textStyle: { fontSize: 13 } },
        tooltip: { trigger: "axis" },
        legend: { show: false },
        dataZoom: [{ type: "inside" }],
        xAxis: { type: "category", data: labels },
        yAxis: { type: "value", name: "value" },
        series: [{ type: "bar", data: values }],
      });
    });
    return () => {
      disposed = true;
      chart?.dispose();
    };
  }, [labels, title, values]);

  return <div ref={ref} style={{ width: "100%", height: 280 }} />;
}
