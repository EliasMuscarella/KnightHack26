import type { NextConfig } from "next";

// RiskDiff renders every data page per request (`export const dynamic = "force-dynamic"`)
// so newly published comparison files appear without a rebuild. Route segment configs
// like `dynamic` are not compatible with Cache Components, so it stays disabled here.
const nextConfig: NextConfig = {
  cacheComponents: false,
  poweredByHeader: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
