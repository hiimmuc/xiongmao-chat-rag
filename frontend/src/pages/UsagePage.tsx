import { useEffect, useState } from "react";
import { api } from "../api";
import UsageDashboard from "../components/UsageDashboard";
import type { UsageData } from "../types";
import { day, usageQuery, type Filters } from "../usage";

const RANGES: [number, string][] = [
  [1, "Today"],
  [7, "7 days"],
  [30, "30 days"],
];

const fresh = (): Filters => ({
  from: day(-29),
  to: day(),
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  provider: "",
  model: "",
  operation: "",
  conversation: "",
});

/** Date range and filters over the usage ledger, rendered by the dashboard. */
export default function UsagePage() {
  const [filters, setFilters] = useState<Filters>(fresh);
  const [range, setRange] = useState(30);
  const [data, setData] = useState<UsageData>();
  const [cursor, setCursor] = useState<string>();
  const [error, setError] = useState("");
  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));

  async function load(f: Filters, page?: string) {
    setError("");
    try {
      const { query, previous } = usageQuery(f);
      const [summary, daily, models, requests, prior] = await Promise.all([
        api("/usage/summary?" + query),
        api("/usage/daily?" + query),
        api("/usage/models?" + query),
        api("/usage/requests?" + query + (page ? "&cursor=" + encodeURIComponent(page) : "")),
        api("/usage/summary?" + previous),
      ]);
      setData({ summary, daily, models, requests, prior });
      setCursor(requests.next_cursor ?? undefined);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void load(filters);
  }, []);

  function preset(days: number) {
    const next = { ...filters, from: day(1 - days), to: day() };
    setRange(days);
    setFilters(next);
    void load(next);
  }

  return (
    <main>
      <div className="usage-head">
        <h1>Usage</h1>
        <div className="seg" role="group" aria-label="Date range">
          {RANGES.map(([days, label]) => (
            <button key={days} aria-pressed={range === days} onClick={() => preset(days)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <details className="more">
        <summary>Filters and custom range</summary>
        <form
          className="filters"
          onSubmit={(e) => {
            e.preventDefault();
            setRange(0);
            void load(filters);
          }}
        >
          <label>
            From
            <input type="date" required value={filters.from} onChange={(e) => set({ from: e.target.value })} />
          </label>
          <label>
            Through
            <input type="date" required value={filters.to} min={filters.from} onChange={(e) => set({ to: e.target.value })} />
          </label>
          <label>
            Timezone
            <input required value={filters.timezone} onChange={(e) => set({ timezone: e.target.value })} />
          </label>
          <label>
            Provider
            <select value={filters.provider} onChange={(e) => set({ provider: e.target.value })}>
              <option value="">All</option>
              <option value="openai">OpenAI</option>
              <option value="gemini">Gemini</option>
            </select>
          </label>
          <label>
            Model ID
            <input value={filters.model} onChange={(e) => set({ model: e.target.value })} />
          </label>
          <label>
            Operation
            <select value={filters.operation} onChange={(e) => set({ operation: e.target.value })}>
              <option value="">All</option>
              <option value="chat">Generation</option>
              <option value="query_embedding">Query embedding</option>
              <option value="document_embedding">Document embedding</option>
            </select>
          </label>
          <label>
            Conversation ID
            <input value={filters.conversation} onChange={(e) => set({ conversation: e.target.value })} />
          </label>
          <button className="primary">Apply</button>
        </form>
      </details>
      {error && <p role="alert">{error}</p>}
      {!data && !error && (
        <p className="state" role="status">
          Loading usage…
        </p>
      )}
      {data && <UsageDashboard data={data} to={filters.to} hasMore={!!cursor} onMore={() => void load(filters, cursor)} />}
    </main>
  );
}
