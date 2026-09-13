export interface PaperAccount {
  id: string; name: string; mode: 'paper'; market: string; currency: string;
  initial_cash: string; status: string;
}
export interface Deployment {
  id: string; account_id: string; mode: 'paper'; strategy: Record<string, unknown>;
  allocation_amount?: string; cash_buffer?: string; desired_state: string;
  observed_state: string; revision: number; pause_epoch: number; last_error?: string | null;
}
export interface HealthResponse { status: string; paper_worker?: string; }
export interface DiagnosticsResponse {
  paper_worker: string; sources: Record<string, string>; live_trading: string; crypto_trading: string;
}
export interface LiveDiagnostic { status: string; source?: string; failures?: number; error?: string; }
export type LiveDiagnosticsResponse = Record<string, LiveDiagnostic>;
export interface AccountSnapshot {
  cash: string; positions: Array<Record<string, string | number>>;
  orders: Array<Record<string, unknown>>; events: Array<Record<string, unknown>>;
  [key: string]: unknown;
}
export interface AccountSnapshotResponse { account: PaperAccount; snapshot: AccountSnapshot; }
