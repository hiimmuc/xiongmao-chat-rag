export type Filters = {
  from: string;
  to: string;
  timezone: string;
  provider: string;
  model: string;
  operation: string;
  conversation: string;
};

export const day = (offset = 0) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const num = (v: unknown) => Number(v) || 0;

export const compact = (n: number) => new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);

export const display = (v: unknown) => (v === null || v === undefined ? "Unknown" : String(v));

export const money = (v: unknown) => {
  if (v === null || v === undefined) return "Unknown";
  const n = num(v);
  return n > 0 && n < 0.0001 ? "<$0.0001" : "$" + n.toFixed(n < 1 ? 4 : 2);
};

/** Query string for a filter set; the previous period has the same length and ends the day before. */
export function usageQuery(f: Filters) {
  const query = new URLSearchParams({
    from: f.from,
    to: f.to,
    timezone: f.timezone,
    ...(f.provider && { provider: f.provider }),
    ...(f.model && { model_id: f.model }),
    ...(f.operation && { operation: f.operation }),
    ...(f.conversation && { conversation_id: f.conversation }),
  });
  const start = +new Date(f.from + "T12:00:00Z");
  const days = Math.round((+new Date(f.to + "T12:00:00Z") - start) / 86400000) + 1;
  const previous = new URLSearchParams(query);
  previous.set("to", new Date(start - 86400000).toISOString().slice(0, 10));
  previous.set("from", new Date(start - days * 86400000).toISOString().slice(0, 10));
  return { query, previous };
}
