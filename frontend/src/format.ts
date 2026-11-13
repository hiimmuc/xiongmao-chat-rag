import type { Usage } from "./types";

export const providerName = (p: string) => (p === "openai" ? "OpenAI" : p === "gemini" ? "Gemini" : p);

export const usd = (n: number) => (n > 0 && n < 0.0001 ? "<$0.0001" : "$" + n.toFixed(n < 1 ? 4 : 2));

export function tokenSummary(u: Usage) {
  if (u.total_tokens == null) return "Tokens unknown";
  const counts = `${u.total_tokens.toLocaleString()} tokens (${u.input_tokens?.toLocaleString()} in, ${u.output_tokens?.toLocaleString()} out)`;
  return u.cost_usd == null ? counts : `${counts} · est. ${usd(Number(u.cost_usd))}`;
}
