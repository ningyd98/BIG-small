self.onmessage = (event: MessageEvent<string>) => {
  const rows = event.data
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as unknown);
  self.postMessage(rows);
};

export {};
