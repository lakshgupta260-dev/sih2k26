import { apiClient } from "./client";
import type {
  ModelVersionRead,
  Page,
  PredictRequest,
  PredictionDetail,
  PredictionRead,
  PredictionRunSummary,
  RiskSummary,
  TrainRequest,
  TrainingOutcome,
} from "@/types/api";

export const predictionApi = {
  train: (projectId: string, payload: TrainRequest = {}) =>
    apiClient
      .post<TrainingOutcome>(`/projects/${projectId}/ml/train`, payload)
      .then((r) => r.data),

  // Both list endpoints below return the Page envelope (verified against the
  // live OpenAPI schema — see FRONTEND_API_INTEGRATION.md), unlike several
  // sibling "list" endpoints elsewhere in the API that return plain arrays.
  listModels: (projectId: string) =>
    apiClient
      .get<Page<ModelVersionRead>>(`/projects/${projectId}/ml/models`, { params: { limit: 200 } })
      .then((r) => r.data.items),

  featureReference: (projectId: string) =>
    apiClient
      .get<Array<Record<string, string>>>(`/projects/${projectId}/ml/features`)
      .then((r) => r.data),

  predict: (projectId: string, scheduleId: string, payload: PredictRequest = {}) =>
    apiClient
      .post<PredictionRunSummary>(
        `/projects/${projectId}/schedules/${scheduleId}/ml/predict`,
        payload,
      )
      .then((r) => r.data),

  listPredictions: (projectId: string, scheduleId: string) =>
    apiClient
      .get<Page<PredictionRead>>(
        `/projects/${projectId}/schedules/${scheduleId}/ml/predictions`,
        { params: { limit: 200 } },
      )
      .then((r) => r.data.items),

  getPrediction: (projectId: string, scheduleId: string, activityId: string) =>
    apiClient
      .get<PredictionDetail>(
        `/projects/${projectId}/schedules/${scheduleId}/ml/predictions/${activityId}`,
      )
      .then((r) => r.data),

  riskSummary: (projectId: string, scheduleId: string) =>
    apiClient
      .get<RiskSummary>(`/projects/${projectId}/schedules/${scheduleId}/ml/risk-summary`)
      .then((r) => r.data),
};
