import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ExperimentDraft } from "../domain/ExperimentDraft";
import { simulationApi } from "./simulationApi";

export function useSimulationCapabilities() {
  return useQuery({
    queryKey: ["simulation", "capabilities"],
    queryFn: () => simulationApi.capabilities(),
    staleTime: 30_000,
  });
}

export function useSimulationScenarios() {
  return useQuery({
    queryKey: ["simulation", "scenarios"],
    queryFn: () => simulationApi.scenarios(),
    staleTime: 30_000,
  });
}

export function useSimulationRuns() {
  return useQuery({
    queryKey: ["simulation", "runs"],
    queryFn: () => simulationApi.runs(),
    refetchInterval: 1_000,
  });
}

export function useSimulationRuntimeHealth() {
  return useQuery({
    queryKey: ["simulation", "runtime", "health"],
    queryFn: () => simulationApi.runtimeHealth(),
    refetchInterval: 2_000,
  });
}

export function useSimulationRuntimeQueue() {
  return useQuery({
    queryKey: ["simulation", "runtime", "queue"],
    queryFn: () => simulationApi.runtimeQueue(),
    refetchInterval: 1_000,
  });
}

export function useSimulationRuntimeWorkers() {
  return useQuery({
    queryKey: ["simulation", "runtime", "workers"],
    queryFn: () => simulationApi.runtimeWorkers(),
    refetchInterval: 2_000,
  });
}

export function useSimulationRunAttempts(runId: string) {
  return useQuery({
    queryKey: ["simulation", "runs", runId, "attempts"],
    queryFn: () => simulationApi.runAttempts(runId),
    enabled: Boolean(runId),
    refetchInterval: 1_000,
  });
}

export function useSubmitSimulationRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draft: ExperimentDraft) => simulationApi.startRun(draft),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["simulation", "runs"] });
    },
  });
}

export function useSubmitSimulationBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draft: ExperimentDraft) => simulationApi.startBatch(draft),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["simulation", "runs"] });
    },
  });
}

export function useCancelSimulationRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => simulationApi.cancelRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["simulation"] });
    },
  });
}

export function useRetrySimulationRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => simulationApi.retryRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["simulation"] });
    },
  });
}

export function useCancelSimulationBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (batchId: string) => simulationApi.cancelBatch(batchId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["simulation"] });
    },
  });
}

export function useRetryFailedSimulationBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (batchId: string) => simulationApi.retryFailedBatch(batchId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["simulation"] });
    },
  });
}
