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
