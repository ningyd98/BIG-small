import type { components } from "../../api/generated/schema";
import type { ExperimentDraft } from "../domain/ExperimentDraft";
import { simulationApi } from "../api/simulationApi";

// ExperimentSubmissionService 只提交高层实验配置；提交前剥离 shell/path/env 等危险字段，
// 浏览器不直接连接 MuJoCo、ROS、MoveIt 或真实机械臂。
export class ExperimentSubmissionService {
  async validate(
    draft: ExperimentDraft,
  ): Promise<components["schemas"]["ValidationResponse"]> {
    return simulationApi.validate(draft);
  }

  async submit(
    draft: ExperimentDraft,
  ): Promise<components["schemas"]["SimulationRunRecord"]> {
    return simulationApi.startRun(stripForbidden(draft));
  }

  async batchSubmit(
    draft: ExperimentDraft,
  ): Promise<components["schemas"]["BatchRecord"]> {
    return simulationApi.startBatch(stripForbidden(draft));
  }

  async cancel(
    runId: string,
  ): Promise<components["schemas"]["SimulationRunRecord"]> {
    return simulationApi.cancelRun(runId);
  }

  async retry(
    runId: string,
  ): Promise<components["schemas"]["SimulationRunRecord"]> {
    return simulationApi.retryRun(runId);
  }

  async batchCancel(
    batchId: string,
  ): Promise<components["schemas"]["BatchRecord"]> {
    return simulationApi.cancelBatch(batchId);
  }

  async retryFailedBatch(
    batchId: string,
  ): Promise<components["schemas"]["BatchRecord"]> {
    return simulationApi.retryFailedBatch(batchId);
  }

  async clone(
    runId: string,
  ): Promise<components["schemas"]["ReproductionResponse"]> {
    return simulationApi.cloneRun(runId);
  }

  async reproduce(
    runId: string,
  ): Promise<components["schemas"]["ReproductionResponse"]> {
    return simulationApi.reproduceRun(runId);
  }
}

function stripForbidden(draft: ExperimentDraft): ExperimentDraft {
  const copy = structuredClone(draft);
  delete (copy as Record<string, unknown>).runner_name;
  delete (copy as Record<string, unknown>).command;
  delete (copy as Record<string, unknown>).script;
  delete (copy as Record<string, unknown>).path;
  return copy;
}
