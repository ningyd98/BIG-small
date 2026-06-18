// 指标聚合 worker，离线计算统计值和分布数据。
type MetricRow = { name: string; value: unknown };

self.onmessage = (event: MessageEvent<MetricRow[]>) => {
  const counts = event.data.reduce<Record<string, number>>(
    (accumulator, metric) => {
      accumulator[metric.name] = (accumulator[metric.name] ?? 0) + 1;
      return accumulator;
    },
    {},
  );
  self.postMessage(counts);
};

export {};
