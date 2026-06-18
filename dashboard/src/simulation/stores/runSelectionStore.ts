// 运行选择 store，记录当前查看的 run/batch，不改变后端状态。
let selectedRunIds: string[] = [];

export function selectRuns(runIds: string[]): void {
  selectedRunIds = [...runIds];
}

export function getSelectedRuns(): string[] {
  return [...selectedRunIds];
}
