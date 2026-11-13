export type Prefs = {
  mode: "light" | "dark" | "system";
  color_theme: "default" | "github" | "claude" | "gemini" | "monokai";
  font_family: "system" | "sans" | "serif" | "mono";
  font_size: "small" | "medium" | "large";
  response_style: "default" | "friendly" | "candid" | "efficient" | "professional" | "analytical";
  notifications: { enabled: boolean; document_processing: boolean; system: boolean };
  models: string[];
};
// Models in the picker until the user changes the selection (keep in sync with backend/app/schemas/account.py).
export const DEFAULT_MODELS = ["gpt-4o", "gpt-4.1", "gpt-4.1-mini", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.6-flash"];
export const DEFAULTS: Prefs = {
  mode: "system",
  color_theme: "claude",
  font_family: "system",
  font_size: "medium",
  response_style: "default",
  notifications: { enabled: true, document_processing: true, system: true },
  models: [...DEFAULT_MODELS],
};
export const THEMES = ["default", "github", "claude", "gemini", "monokai"] as const;
export const STYLES: [Prefs["response_style"], string, string][] = [
  ["default", "Default", "Balanced and neutral."],
  ["friendly", "Friendly", "Warm and conversational."],
  ["candid", "Candid", "Direct, with honest assessments."],
  ["efficient", "Efficient", "Short answers, no filler."],
  ["professional", "Professional", "Polished and precise."],
  ["analytical", "Analytical", "Step-by-step reasoning."],
];
const KEY = "prefs";
export function cached(): Prefs {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return DEFAULTS;
  }
}
// Sets the root data attributes the stylesheet keys on; the cache avoids a wrong-theme flash on load.
export function apply(p: Prefs) {
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  const root = document.documentElement.dataset;
  root.theme = p.mode === "system" ? (dark ? "dark" : "light") : p.mode;
  root.palette = p.color_theme;
  root.font = p.font_family;
  root.size = p.font_size;
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {}
}
apply(cached());
