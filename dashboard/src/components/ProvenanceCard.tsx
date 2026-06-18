import { Card, Descriptions } from "antd";

// 证据溯源卡片展示提交和源码树哈希，帮助区分当前运行结果与历史 artifact。
type ProvenanceCardProps = {
  commit: string;
  sourceTreeHash: string;
  worktreeClean: boolean;
};

export function ProvenanceCard({
  commit,
  sourceTreeHash,
  worktreeClean,
}: ProvenanceCardProps) {
  return (
    <Card title="证据溯源" size="small">
      <Descriptions size="small" column={1}>
        <Descriptions.Item label="软件提交">{commit}</Descriptions.Item>
        <Descriptions.Item label="源码树哈希">
          {sourceTreeHash}
        </Descriptions.Item>
        <Descriptions.Item label="工作区是否干净">
          {String(worktreeClean)}
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
