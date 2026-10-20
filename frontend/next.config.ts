import type { NextConfig } from "next";

// Static export served by FastAPI (PLAN §10): no API routes, middleware or rewrites.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
