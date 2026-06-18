// ExportService 在浏览器侧导出报告前做最后一道脱敏；后端 artifact 仍是权威来源。
const sensitiveKeys = new Set([
  "token",
  "credential",
  "password",
  "secret",
  "controller_config",
  "ip",
]);

export class ExportService {
  manifestJson(value: unknown): string {
    return JSON.stringify(redact(value), null, 2);
  }
}

function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        sensitiveKeys.has(key.toLowerCase()) ? "<redacted>" : redact(item),
      ]),
    );
  }
  if (typeof value === "string") {
    return value
      .replace(/\/home\/[^/\s]+/g, "$HOME")
      .replace(/[A-Za-z]:\\Users\\[^\\\s]+/g, "$HOME")
      .replace(/token=([^&\s]+)/gi, "token=<redacted>");
  }
  return value;
}
