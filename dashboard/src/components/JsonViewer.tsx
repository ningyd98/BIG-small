// JSON 展示组件，用于只读呈现证据和诊断载荷。
import { Card } from "antd";

type JsonViewerProps = {
  value: unknown;
};

export function JsonViewer({ value }: JsonViewerProps) {
  return (
    <Card size="small">
      <pre style={{ margin: 0, maxHeight: 360, overflow: "auto" }}>
        {JSON.stringify(value, null, 2)}
      </pre>
    </Card>
  );
}
