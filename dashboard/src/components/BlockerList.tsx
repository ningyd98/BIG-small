import { Empty } from "antd";

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
