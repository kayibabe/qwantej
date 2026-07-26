import { useId } from 'react'

export default function QwantejLogo({ className = '', style = {} }) {
  const raw = useId()
  const uid = raw.replace(/[^a-zA-Z0-9]/g, '')
  const ringId = `${uid}ring`
  const pxId   = `${uid}px`

  const dots = [[97, 106], [112, 80], [126, 93], [143, 68]]

  return (
    <svg
      viewBox="0 0 240 228"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      style={style}
      role="img"
      aria-label="Qwantej — Intelligence Beyond Numbers."
    >
      <defs>
        {/* Ring gradient: indigo-black → royal blue → electric blue, bottom-left to top-right */}
        <linearGradient id={ringId} x1="0%" y1="85%" x2="100%" y2="15%">
          <stop offset="0%"   style={{ stopColor: 'var(--qlogo-a)' }} />
          <stop offset="52%"  style={{ stopColor: 'var(--qlogo-b)' }} />
          <stop offset="100%" style={{ stopColor: 'var(--qlogo-c)' }} />
        </linearGradient>
        {/* Pixel gradient: mid-blue → bright, inner to outer scatter */}
        <linearGradient id={pxId} x1="100%" y1="100%" x2="0%" y2="0%">
          <stop offset="0%"   style={{ stopColor: 'var(--qlogo-b)' }} />
          <stop offset="100%" style={{ stopColor: 'var(--qlogo-c)' }} stopOpacity="0.65" />
        </linearGradient>
      </defs>

      {/* ── Q ring ── */}
      <circle
        cx="130" cy="88" r="62"
        fill="none"
        stroke={`url(#${ringId})`}
        strokeWidth="17"
      />

      {/* ── Q tail — starts inside the ring, crosses the edge, extends lower-right ── */}
      <line
        x1="163" y1="121" x2="196" y2="154"
        stroke={`url(#${ringId})`}
        strokeWidth="17"
        strokeLinecap="round"
      />

      {/* ── Pixel scatter — upper-left quadrant, dissolving outward ── */}

      {/* Group A: largest, nearest the ring edge */}
      <rect x="70" y="50" width="7" height="7" fill={`url(#${pxId})`} />
      <rect x="79" y="57" width="6" height="6" fill={`url(#${pxId})`} />
      <rect x="63" y="57" width="6" height="6" fill={`url(#${pxId})`} />

      {/* Group B: medium */}
      <rect x="57" y="43" width="5" height="5" style={{ fill: 'var(--qlogo-b)' }} />
      <rect x="50" y="51" width="5" height="5" style={{ fill: 'var(--qlogo-b)' }} />
      <rect x="65" y="49" width="4" height="4" style={{ fill: 'var(--qlogo-b)' }} />
      <rect x="44" y="57" width="4" height="4" style={{ fill: 'var(--qlogo-b)' }} opacity="0.85" />
      <rect x="54" y="63" width="4" height="4" style={{ fill: 'var(--qlogo-b)' }} opacity="0.85" />

      {/* Group C: smaller, fading */}
      <rect x="38" y="41" width="4" height="4" style={{ fill: 'var(--qlogo-pixel)' }} opacity="0.75" />
      <rect x="31" y="49" width="3" height="3" style={{ fill: 'var(--qlogo-pixel)' }} opacity="0.70" />
      <rect x="44" y="67" width="3" height="3" style={{ fill: 'var(--qlogo-pixel)' }} opacity="0.65" />
      <rect x="35" y="61" width="3" height="3" style={{ fill: 'var(--qlogo-pixel)' }} opacity="0.65" />
      <rect x="25" y="41" width="3" height="3" style={{ fill: 'var(--qlogo-pixel)' }} opacity="0.60" />

      {/* Group D: tiny, outermost */}
      <rect x="21" y="51" width="2" height="2" style={{ fill: 'var(--qlogo-pixel)' }} opacity="0.50" />
      <rect x="16" y="45" width="2" height="2" style={{ fill: 'var(--qlogo-pixel)' }} opacity="0.45" />
      <rect x="27" y="63" width="2" height="2" style={{ fill: 'var(--qlogo-pixel)' }} opacity="0.45" />
      <rect x="13" y="55" width="2" height="2" style={{ fill: 'var(--qlogo-pixel)' }} opacity="0.35" />

      {/* ── Analytics chart inside Q ── */}
      <polyline
        points="97,106 112,80 126,93 143,68"
        fill="none"
        style={{ stroke: 'var(--qlogo-chart)' }}
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {dots.map(([x, y], i) => (
        <circle
          key={i}
          cx={x} cy={y} r="5"
          style={{ fill: 'var(--qlogo-dot-fill)', stroke: 'var(--qlogo-chart)' }}
          strokeWidth="2"
        />
      ))}

      {/* ── Wordmark ── */}
      <text
        x="120" y="196"
        textAnchor="middle"
        fontFamily="'Segoe UI', system-ui, -apple-system, sans-serif"
        fontWeight="700"
        fontSize="30"
        letterSpacing="-0.5"
        style={{ fill: 'var(--text-h)' }}
      >
        Qwantej
      </text>

      {/* ── Tagline ── */}
      <text
        x="120" y="217"
        textAnchor="middle"
        fontFamily="'Segoe UI', system-ui, -apple-system, sans-serif"
        fontWeight="500"
        fontSize="9"
        letterSpacing="0.6"
        style={{ fill: 'var(--qlogo-tagline)' }}
      >
        — Intelligence Beyond Numbers. —
      </text>
    </svg>
  )
}
