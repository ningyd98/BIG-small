// 阻塞项列表组件：只展示后端判定的 blocker，不在前端重新推导安全结论。
import { Empty } from "antd";

// 阻塞项组件只呈现后端判定结果，避免前端自行推断安全或环境状态。
type BlockerListProps = {
  blockers: string[];
};

export function BlockerList({ blockers }: BlockerListProps) {
  if (blockers.length === 0) {
    return (
      <Empty
        description="当前没有新的软件侧阻塞项"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  return (
    <ul className="plain-list compact-list">
      {blockers.map((blocker) => (
        <li key={blocker}>{blocker}</li>
      ))}
    </ul>
  );
}
