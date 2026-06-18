let selectedRunIds: string[] = [];

export function selectRuns(runIds: string[]): void {
  selectedRunIds = [...runIds];
}

export function getSelectedRuns(): string[] {
  return [...selectedRunIds];
}
