import { Result } from "antd";

// 404 页面只引导回控制台导航，不暴露内部路由或 API 结构。
export function NotFoundPage() {
  return (
    <Result
      status="404"
      title="页面不存在"
      subTitle="请从左侧导航选择控制台页面。"
    />
  );
}
