import { Result } from "antd";

export function NotFoundPage() {
  return (
    <Result
      status="404"
      title="页面不存在"
      subTitle="请从左侧导航选择控制台页面。"
    />
  );
}
