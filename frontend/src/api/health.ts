import { apiClient } from "./client";
import type { HealthResponse, ReadinessResponse } from "@/types/api";

export const healthApi = {
  live: () => apiClient.get<HealthResponse>("/health").then((r) => r.data),
  ready: () => apiClient.get<ReadinessResponse>("/health/ready").then((r) => r.data),
};
