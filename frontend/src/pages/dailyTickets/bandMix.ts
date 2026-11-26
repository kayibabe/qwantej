import type { SelectionSummary } from "../../lib/api";

/**
 * Band mix: the five exact model-probability × market-implied pairs captured
 * from the saved filter. Each pair can be selected independently; selected
 * pairs combine with OR (any pair qualifies a match). Bands match the backend's
 * 5pp buckets in app/services/performance.py, so this view agrees with
 * Validate's combined matrix. QwantEj band here means the model's predicted
 * probability, not the Q-score quality gate.
 */
export const BAND_MIX_PAIRS: [string, string][] = [
  ["<50", "85-90"],
  ["50-55", "90-95"],
  ["55-60", "95-100"],
  ["60-65", "90-95"],
  ["95-100", "70-75"],
];

export function bandMixPairLabel(index: number) {
  const [model, market] = BAND_MIX_PAIRS[index];
  return `${model}% × ${market}%`;
}

export const BAND_MIX_LABEL = BAND_MIX_PAIRS.map((_, index) => bandMixPairLabel(index)).join(" · ");
export const ALL_BAND_MIX_PAIRS = BAND_MIX_PAIRS.map((_, index) => index);

/** New links use "p<index>" tokens; the legacy "1" still means every pair. */
export function encodeBandMixPairs(pairs: number[]): string {
  return pairs.map((index) => `p${index}`).join(",");
}

export function parseBandMixPairs(value: string | null): number[] {
  if (!value) return [];
  if (value === "1") return [...ALL_BAND_MIX_PAIRS];
  const pairs = value
    .split(",")
    .map((token) => token.trim().replace(/^p/i, ""))
    .filter((token) => token !== "")
    .map(Number)
    .filter((index) => Number.isInteger(index) && index >= 0 && index < BAND_MIX_PAIRS.length);
  return [...new Set(pairs)].sort((left, right) => left - right);
}

/** Bookmaker implied probability (margin included), as displayed per pick. */
export function impliedProbability(row: SelectionSummary) {
  return row.source_implied_probability ?? row.avg_implied ?? Number.NaN;
}

/** Same 5pp buckets as performance._probability_band(), including the 95+ top band. */
export function probabilityBand(value: number | null | undefined): string | null {
  if (value == null || !Number.isFinite(value)) return null;
  const percent = value * 100;
  if (percent < 50) return "<50";
  const lower = Math.min(95, Math.floor(percent / 5) * 5);
  return `${lower}-${lower + 5}`;
}

/** A row qualifies when it fits ANY selected pair (default: all five). */
export function matchesBandMix(row: SelectionSummary, selectedPairs: readonly number[] = ALL_BAND_MIX_PAIRS) {
  const modelBand = probabilityBand(row.model_probability);
  const marketBand = probabilityBand(impliedProbability(row));
  return modelBand != null && marketBand != null
    && selectedPairs.some((index) => {
      const pair = BAND_MIX_PAIRS[index];
      return pair != null && pair[0] === modelBand && pair[1] === marketBand;
    });
}
