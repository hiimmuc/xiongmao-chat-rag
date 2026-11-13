export type Chat = { id: string; title: string; document_ids: string[] };
export type Model = { id: string; label: string; provider: string };
export type Doc = {
  id: string;
  name: string;
  state: string;
  bytes: number;
  created_at?: string;
  error_code?: string;
};
export type Usage = {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  cost_usd: string | null;
};
export type Source = { id: string; name: string; page?: number | null; snippet?: string };
export type Message = {
  id: string;
  role: string;
  content: string;
  generation_id?: string;
  status?: string;
  model_id?: string;
  citations?: Source[];
  usage?: Usage | null;
};

export type UsageSummary = {
  confirmed_requests: number;
  unknown_dispatches: number;
  known_input_tokens: number;
  known_output_tokens: number;
  known_total_tokens: number | null;
  known_cost_usd: string | null;
  unknown_usage_records: number;
  unpriced_records: number;
  complete: boolean;
};
export type UsageDay = UsageSummary & { date: string };
export type UsageModel = UsageSummary & { provider: string; model_id: string; operation: string };
export type UsageCall = Record<string, unknown> & { id: string };
export type UsageData = {
  summary: UsageSummary;
  daily: { items: UsageDay[] };
  models: { items: UsageModel[] };
  requests: { items: UsageCall[]; next_cursor: string | null };
  prior: UsageSummary;
};
