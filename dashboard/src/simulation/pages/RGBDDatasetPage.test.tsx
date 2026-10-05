import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DatasetEvidenceSummary } from "./RGBDDatasetPage";

describe("dataset evidence", () => {
  it("shows published progress without claiming physical task success", () => {
    render(<DatasetEvidenceSummary job={{
      job_id: "job-1", dataset_id: "run-1", status: "SUCCEEDED",
      requested_groups: 100, published_groups: 12, published_samples: 15,
      positive_samples: 8, negative_samples: 7, sample_ids: [],
      model_calls: 0, task_success: false, task_execution: "NOT_EXECUTED",
      split_group_counts: {}, cancel_requested: false, error_code: "",
    }} />);
    expect(screen.getByText("12 / 100")).toBeInTheDocument();
    expect(screen.getByText(/物理任务未执行/)).toBeInTheDocument();
    expect(screen.queryByText("抓取成功")).not.toBeInTheDocument();
  });
});
