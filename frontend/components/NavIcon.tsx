type NavIconName = "dashboard" | "accumulators" | "predictions" | "settlements" | "performance" | "models"

export default function NavIcon({ name }: { name: NavIconName }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.8,
  }

  return (
    <svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true" focusable="false">
      {name === "dashboard" && <>
        <rect {...common} x="4" y="4" width="6" height="6" rx="1" />
        <rect {...common} x="14" y="4" width="6" height="6" rx="1" />
        <rect {...common} x="4" y="14" width="6" height="6" rx="1" />
        <rect {...common} x="14" y="14" width="6" height="6" rx="1" />
      </>}
      {name === "accumulators" && <>
        <path {...common} d="m12 3 8 4.5-8 4.5-8-4.5L12 3Z" />
        <path {...common} d="m4 12 8 4.5 8-4.5M4 16.5l8 4.5 8-4.5" />
      </>}
      {name === "predictions" && <>
        <path {...common} d="M4 17.5 9 12l3.5 3 7.5-8" />
        <path {...common} d="M16 7h4v4" />
        <path {...common} d="M4 20h16" />
      </>}
      {name === "settlements" && <>
        <circle {...common} cx="12" cy="12" r="8.5" />
        <path {...common} d="m8 12 2.6 2.6L16.5 9" />
      </>}
      {name === "performance" && <>
        <path {...common} d="M5 17 17 5M9 5h8v8" />
        <path {...common} d="M5 5v14h14" />
      </>}
      {name === "models" && <>
        <circle {...common} cx="12" cy="12" r="3" />
        <circle {...common} cx="12" cy="4.5" r="1.5" />
        <circle {...common} cx="5.5" cy="16" r="1.5" />
        <circle {...common} cx="18.5" cy="16" r="1.5" />
        <path {...common} d="m12 9V6M9.5 13.5l-2.8 1.7M14.5 13.5l2.8 1.7" />
      </>}
    </svg>
  )
}
