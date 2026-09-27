import type { PredictionOut } from "./types"

const MARKET_LABEL: Record<string, string> = {
  "1X2": "Match result",
  DOUBLE_CHANCE: "Double chance",
  BTTS: "Both teams to score",
  TOTALS: "Total goals",
}

export function marketLabel(market: string): string {
  return MARKET_LABEL[market.toUpperCase()] ?? market
}

/** Human selection, e.g. "Arsenal to win", "Draw or Chelsea", "Over 2.5". */
export function selectionLabel(
  p: Pick<PredictionOut, "market" | "selection" | "line" | "home_team" | "away_team">,
): string {
  const home = p.home_team ?? "Home"
  const away = p.away_team ?? "Away"
  const sel = p.selection.toLowerCase()
  switch (p.market.toUpperCase()) {
    case "1X2":
      return sel === "home" ? `${home} to win` : sel === "away" ? `${away} to win` : sel === "draw" ? "Draw" : p.selection
    case "DOUBLE_CHANCE":
      return sel === "1x" ? `${home} or draw` : sel === "x2" ? `Draw or ${away}` : sel === "12" ? `${home} or ${away}` : p.selection
    case "BTTS":
      return sel === "yes" ? "Both teams score" : sel === "no" ? "Not both teams score" : p.selection
    case "TOTALS": {
      const side = sel === "over" ? "Over" : sel === "under" ? "Under" : p.selection
      return p.line !== null ? `${side} ${p.line}` : side
    }
    default:
      return p.selection
  }
}
