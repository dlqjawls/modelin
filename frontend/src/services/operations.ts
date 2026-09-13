import type { AxiosRequestConfig } from 'axios';
import type { AccountSnapshotResponse, Deployment, DiagnosticsResponse, HealthResponse, LiveDiagnosticsResponse, PaperAccount } from '../contracts/operations';
import { apiClient } from './client';

export const operationsApi = {
  health: () => apiClient.get<HealthResponse>('/api/health'),
  accounts: () => apiClient.get<PaperAccount[]>('/api/v1/accounts'),
  deployments: () => apiClient.get<Deployment[]>('/api/v1/deployments'),
  createPaperAccount: (body: { name: string; market: string; currency: string; initial_cash: string }) =>
    apiClient.post<PaperAccount>('/api/v1/accounts/paper', body),
  snapshot: (accountId: string, config?: AxiosRequestConfig) =>
    apiClient.get<AccountSnapshotResponse>(`/api/v1/accounts/${accountId}/snapshot`, config),
  deployment: (id: string) => apiClient.get<Deployment>(`/api/v1/deployments/${id}`),
  command: (id: string, type: 'START' | 'PAUSE' | 'CANCEL_OPEN' | 'LIQUIDATE' | 'RESUME' | 'ARCHIVE') =>
    apiClient.post<Deployment>(`/api/v1/deployments/${id}/commands`, { type, reason: `UI:${type}` }),
  diagnostics: () => apiClient.get<DiagnosticsResponse>('/api/v1/diagnostics'),
  liveDiagnostics: () => apiClient.get<LiveDiagnosticsResponse>('/api/v1/diagnostics/live'),
};
