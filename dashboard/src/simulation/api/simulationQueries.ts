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
