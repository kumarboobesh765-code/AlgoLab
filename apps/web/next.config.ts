import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for the slim Docker runner image (infrastructure/docker/web.Dockerfile)
  output: "standalone",
};

export default nextConfig;
