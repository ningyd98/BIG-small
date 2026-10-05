import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Form, Image, Input, InputNumber,
  Progress, Select, Space, Tag, Typography } from "antd";
import { useState } from "react";

import { rgbdDatasetApi, type DatasetJob, type DatasetJobRequest } from "../api/rgbdDatasetApi";

export function DatasetEvidenceSummary({ job }: { job: DatasetJob }) {
  return <Card title="已发布数据">
    <Space wrap><Tag>{job.status}</Tag><Tag color="blue">离线相机采集</Tag>
      <Typography.Text>物理任务未执行；数据生成完成不代表抓取成功。</Typography.Text></Space>
    <Progress percent={Math.round(job.published_groups / job.requested_groups * 100)}
      format={() => `${job.published_groups} / ${job.requested_groups}`} />
    <Descriptions column={2} items={[
      { key: "samples", label: "已发布帧", children: job.published_samples },
      { key: "positive", label: "感知正例", children: job.positive_samples },
      { key: "negative", label: "保留负例", children: job.negative_samples },
      { key: "model", label: "模型请求", children: job.model_calls },
      { key: "splits", label: "场景组划分", children: Object.entries(job.split_group_counts)
        .map(([key, value]) => `${key}: ${value}`).join(" / ") || "划分尚未发布" },
    ]} />
    {job.error_code && <Alert type="warning" title={job.error_code} />}
  </Card>;
}

const terminalStatuses = new Set(["SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT",
  "BLOCKED_BY_ENV", "INTERRUPTED"]);

export function RGBDDatasetPage() {
  const [jobId, setJobId] = useState("");
  const [enteredJob, setEnteredJob] = useState("");
  const [selectedSample, setSelectedSample] = useState("");
  const create = useMutation({ mutationFn: rgbdDatasetApi.create,
    onSuccess: (job) => { setJobId(job.job_id); setSelectedSample(""); } });
  const jobQuery = useQuery({ queryKey: ["rgbd-dataset", jobId], enabled: Boolean(jobId),
    queryFn: () => rgbdDatasetApi.job(jobId),
    refetchInterval: (query) => terminalStatuses.has(query.state.data?.status ?? "") ? false : 2000 });
  const job = jobQuery.data;
  const sampleId = selectedSample || job?.sample_ids[0] || "";
  const sample = useQuery({ queryKey: ["rgbd-sample", job?.dataset_id, sampleId],
    enabled: Boolean(job?.dataset_id && sampleId),
    queryFn: () => rgbdDatasetApi.sample(job!.dataset_id, sampleId) });
  const cancel = useMutation({ mutationFn: () => rgbdDatasetApi.cancel(jobId),
    onSuccess: () => { void jobQuery.refetch(); } });
  const error = create.error || jobQuery.error || sample.error || cancel.error;

  return <Space orientation="vertical" size="large" style={{ width: "100%" }}>
    <Typography.Title level={3}>RGB-D 数据工作台</Typography.Title>
    <Alert type="info" showIcon title="采集 RGB、米制深度与标定，不需要视觉模型。正例、负例和取消前已发布的数据均保留。" />
    {error && <Alert type="error" title={error.message} />}
    <Card title="创建数据作业">
      <Form<DatasetJobRequest> layout="inline" initialValues={{ config_id: "SMOKE", groups: 100,
        seed: 0, width: 320, height: 240 }} onFinish={(values) => create.mutate(values)}>
        <Form.Item name="config_id" label="采样配置"><Select style={{ width: 150 }} options={[
          { value: "SMOKE", label: "冒烟采样" }, { value: "VALIDATION", label: "验证采样" },
          { value: "FULL", label: "全量采样" }]} /></Form.Item>
        <Form.Item name="groups" label="独立场景组"><InputNumber min={1} max={10000} /></Form.Item>
        <Form.Item name="seed" label="种子"><InputNumber min={0} max={2147483647} /></Form.Item>
        <Form.Item name="width" label="宽"><InputNumber min={1} max={1280} /></Form.Item>
        <Form.Item name="height" label="高"><InputNumber min={1} max={720} /></Form.Item>
        <Button type="primary" htmlType="submit" loading={create.isPending}>启动采集</Button>
      </Form>
    </Card>
    <Space><Input placeholder="输入已有作业 ID" value={enteredJob}
      onChange={(event) => setEnteredJob(event.target.value)} />
      <Button disabled={!enteredJob.trim()} onClick={() => {
        setJobId(enteredJob.trim()); setSelectedSample("");
      }}>查看作业</Button>
      {job && <Button danger disabled={terminalStatuses.has(job.status) || job.cancel_requested}
        loading={cancel.isPending} onClick={() => cancel.mutate()}>取消采集</Button>}
    </Space>
    {job && <>
      <Typography.Text copyable>作业 ID：{job.job_id}</Typography.Text>
      <DatasetEvidenceSummary job={job} />
      <Card title="已发布样本预览">
        <Select style={{ minWidth: 360 }} value={sampleId || undefined} placeholder="等待样本发布"
          options={job.sample_ids.map((id) => ({ value: id, label: id }))}
          onChange={setSelectedSample} showSearch />
        {sample.data && <>
          <Space wrap style={{ marginTop: 16 }}><Tag>{sample.data.status}</Tag>
            <Tag>{sample.data.split ?? "划分未发布"}</Tag>
            <Typography.Text>深度 {sample.data.depth_min_m?.toFixed(3) ?? "N/A"}–
              {sample.data.depth_max_m?.toFixed(3) ?? "N/A"} m；有效比例
              {(sample.data.valid_depth_fraction * 100).toFixed(1)}%</Typography.Text></Space>
          <Space wrap style={{ display: "flex", marginTop: 16 }}>
            <div><Typography.Paragraph>RGB</Typography.Paragraph>
              <Image width={320} src={sample.data.rgb_data_url} alt="真实 RGB 帧" /></div>
            <div><Typography.Paragraph>深度辅助图</Typography.Paragraph>
              <Image width={320} src={sample.data.depth_data_url} alt="深度可视化" /></div>
          </Space>
          <Typography.Paragraph>拒绝原因：{sample.data.rejection_reasons.join("、") || "无"}</Typography.Paragraph>
          <Typography.Text type="secondary">只读离线预览；原始采集时间与校验和保留。</Typography.Text>
        </>}
      </Card>
    </>}
  </Space>;
}
