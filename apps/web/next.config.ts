import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for the slim Docker runner image (infrastructure/docker/web.Dockerfile)
  output: "standalone",
  // Allow the dev server to be reached from non-localhost hosts (e.g. a LAN IP
  // or forwarded port). Next blocks cross-origin dev chunk loads by default.
  allowedDevOrigins: ["*", "10.124.142.30", "localhost", "127.0.0.1"],
};

export default nextConfig;
