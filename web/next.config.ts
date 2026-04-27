import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  compress: true,
  productionBrowserSourceMaps: false,
  output: "standalone",
  experimental: {
    optimizePackageImports: ["react", "react-dom"],
  },
};

export default withSentryConfig(nextConfig, {
  silent: true,
});
