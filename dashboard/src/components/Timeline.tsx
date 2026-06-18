// 时间线组件，用于展示审计事件、故障和运行状态变化。
import { Timeline as AntTimeline } from "antd";

type TimelineProps = {
  items: Array<{ label: string; detail: string }>;
};

export function Timeline({ items }: TimelineProps) {
  return (
    <AntTimeline
      items={items.map((item) => ({
        children: (
          <>
            <strong>{item.label}</strong>
            <div>{item.detail}</div>
          </>
        ),
      }))}
    />
  );
}
