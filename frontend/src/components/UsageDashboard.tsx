import { useState, type PointerEvent } from "react";
import { compact, day, display, money, num } from "../usage";
import type { UsageCall, UsageData, UsageModel } from "../types";

const FIELD = { tokens: "known_total_tokens", requests: "confirmed_requests", cost: "known_cost_usd" } as const;
type Metric = keyof typeof FIELD;
const format = (m: Metric, v: unknown) => (m === "cost" ? money(v) : num(v).toLocaleString());

/** Headline figures, a per-day chart, a per-model ranking and the invocation table. */
export default function UsageDashboard({ data, to, hasMore, onMore }: { data: UsageData; to: string; hasMore: boolean; onMore: () => void }) {
  const [metric, setMetric] = useState<Metric>("tokens");
  const [pick, setPick] = useState<string>();
  const { summary: s, daily, prior } = data;
  const items = daily.items;
  const field = FIELD[metric];
  const max = Math.max(1, ...items.map((r) => num(r[field])));
  const models = tokensByModel(data.models.items);
  const top = Math.max(1, ...models.map((m) => m.tokens));
  const change = num(s.confirmed_requests) - num(prior.confirmed_requests);
  const percent = num(prior.confirmed_requests) > 0 ? (change / num(prior.confirmed_requests)) * 100 : null;
  const input = num(s.known_input_tokens);
  const output = num(s.known_output_tokens);
  const gaps = num(s.unknown_usage_records) + num(s.unpriced_records) + num(s.unknown_dispatches);
  const shown = items.find((r) => r.date === pick);

  const scrub = (e: PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.min(items.length - 1, Math.max(0, Math.floor(((e.clientX - r.left) / r.width) * items.length)));
    if (items[i]) setPick(items[i].date);
  };

  return (
    <>
      <dl className="kpis">
        <div className="kpi">
          <dt>Requests</dt>
          <dd>{display(s.confirmed_requests)}</dd>
          <small>
            {percent === null ? `${change >= 0 ? "+" : ""}${change} vs previous period (was 0)` : `${percent >= 0 ? "+" : ""}${percent.toFixed(0)}% vs previous period`}
          </small>
        </div>
        <div className="kpi">
          <dt>Total tokens</dt>
          <dd>{s.known_total_tokens == null ? "Unknown" : compact(num(s.known_total_tokens))}</dd>
          <small>
            {compact(input)} in · {compact(output)} out
          </small>
          <div className="split" aria-hidden="true">
            <i style={{ width: (input / Math.max(1, input + output)) * 100 + "%" }} />
            <i style={{ width: (output / Math.max(1, input + output)) * 100 + "%" }} />
          </div>
        </div>
        <div className="kpi">
          <dt>Estimated cost{gaps > 0 ? " (known subtotal)" : ""}</dt>
          <dd>{num(s.known_cost_usd) === 0 && num(s.unpriced_records) > 0 ? "Not priced" : money(s.known_cost_usd)}</dd>
          <small>{num(s.unpriced_records) ? `${s.unpriced_records} calls without a configured price` : "All calls priced"}</small>
        </div>
      </dl>
      {gaps > 0 && (
        <p className="note">
          Totals are incomplete: {s.unknown_usage_records} calls with unknown usage, {s.unpriced_records} without a price, {s.unknown_dispatches} unconfirmed dispatches.
        </p>
      )}
      <section className="panel" aria-label="Daily activity">
        <div className="panel-head">
          <h2>Daily activity</h2>
          <div className="seg" role="group" aria-label="Metric">
            {(Object.keys(FIELD) as Metric[]).map((m) => (
              <button key={m} aria-pressed={metric === m} onClick={() => setMetric(m)}>
                {m[0].toUpperCase() + m.slice(1)}
              </button>
            ))}
          </div>
        </div>
        {to === day() && <p className="note">Today is a partial day.</p>}
        <p className="readout" role="status">
          {shown ? `${shown.date}: ${format(metric, shown[field])}${metric === "cost" ? "" : " " + metric}` : "Select a day for details."}
        </p>
        {items.length ? (
          <>
            <div className="bars" onPointerDown={scrub} onPointerMove={(e) => e.buttons && scrub(e)}>
              {items.map((r) => (
                <button
                  key={r.date}
                  className="bar"
                  aria-pressed={pick === r.date}
                  aria-label={`${r.date}: ${format(metric, r[field])}`}
                  title={`${r.date}: ${format(metric, r[field])}`}
                  onClick={() => setPick(pick === r.date ? undefined : r.date)}
                >
                  <i style={{ height: Math.max(1, (num(r[field]) / max) * 100) + "%" }} />
                </button>
              ))}
            </div>
            <div className="axis">
              <span>{items[0].date}</span>
              <span>{items[items.length - 1].date}</span>
            </div>
          </>
        ) : (
          <p className="state">No activity in this range.</p>
        )}
      </section>
      <section className="panel" aria-label="By model">
        <div className="panel-head">
          <h2>By model</h2>
          <span className="readout">Tokens, estimated cost</span>
        </div>
        {models.length ? (
          <ul className="rank">
            {models.map((m) => (
              <li key={m.provider + m.model_id} className={m.provider}>
                <span>{m.model_id}</span>
                <small>
                  {m.tokens.toLocaleString()} tokens · {money(m.cost || null)} · {m.requests} req
                </small>
                <span className="track">
                  <i style={{ width: (m.tokens / top) * 100 + "%" }} />
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="state">No activity in this range.</p>
        )}
      </section>
      <details className="more">
        <summary>Invocation detail</summary>
        <CallTable rows={data.requests.items} />
        {hasMore && <button onClick={onMore}>Next page</button>}
      </details>
    </>
  );
}

const COLUMNS = ["created_at", "provider", "model_id", "operation", "status", "input_tokens", "output_tokens", "cost_usd"];

function CallTable({ rows }: { rows: UsageCall[] }) {
  if (!rows.length) return <p>No activity for these filters.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {COLUMNS.map((c) => (
              <th key={c}>{c.replaceAll("_", " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              {COLUMNS.map((c) => (
                <td key={c}>{display(r[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Sum each model's rows across operations (chat, query embedding, indexing), largest first. */
function tokensByModel(rows: UsageModel[]) {
  const totals = new Map<string, { provider: string; model_id: string; tokens: number; cost: number; requests: number }>();
  for (const r of rows) {
    const key = r.provider + "/" + r.model_id;
    const t = totals.get(key) ?? { provider: r.provider, model_id: r.model_id, tokens: 0, cost: 0, requests: 0 };
    t.tokens += num(r.known_total_tokens);
    t.cost += num(r.known_cost_usd);
    t.requests += num(r.confirmed_requests);
    totals.set(key, t);
  }
  return [...totals.values()].sort((a, b) => b.tokens - a.tokens);
}
