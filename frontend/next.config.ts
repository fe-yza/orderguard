import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output keeps the production Docker image small (copies only
  // the built app + its resolved node_modules subset, not the full
  // workspace) — see frontend/Dockerfile.
  output: "standalone",
};

export default nextConfig;
