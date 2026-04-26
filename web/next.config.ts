import type { NextConfig } from "next";

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

export default nextConfig;
