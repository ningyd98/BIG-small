// JSONL 解析 worker，分块解析事件文件以保护浏览器主线程。
self.onmessage = (event: MessageEvent<string>) => {
  const rows = event.data
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as unknown);
  self.postMessage(rows);
};

export {};
