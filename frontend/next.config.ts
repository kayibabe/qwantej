import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Ticket results and Settlements were folded into Performance as tabs.
  // Keep old links and bookmarks working; incoming query strings (e.g.
  // ?by=month or ?type=accumulator&outcome=win) are passed through.
  async redirects() {
    return [
      { source: "/accumulators/results", destination: "/performance?tab=periods", permanent: false },
      { source: "/settlements", destination: "/performance?tab=settlements", permanent: false },
    ];
  },
};

export default nextConfig;
