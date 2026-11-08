export interface DailyTicketsPageProps {
  date: string;
  initialTab?: DailyTab;
  /** "overview" is the public decision page; "research" is the internal workspace. */
  mode?: "overview" | "research";
  onTabChange?: (tab: DailyTab) => void;
  onUpgrade?: () => void;
}

export type DailyTab =
  | "tickets"
  | "picks"
  | "fixtures"
  | "passed"
  | "odds-policy"
  | "market-roi";

export type MatchDisplayState =
  "finished" | "live" | "scheduled" | "postponed" | "cancelled" | "abandoned" | "awarded";

export type SelectionDisplayState = "won" | "lost" | "void" | "inplay" | "pending";
