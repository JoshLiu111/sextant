import type { NextConfig } from "next";

// Outside Vercel (local dev, CI), proxy browser calls to /api/compute/* to the
// local FastAPI service. On Vercel the top-level rewrite in /vercel.json routes
// /api/compute/* to the compute service before Next.js sees the request.
const computeUrl = process.env.COMPUTE_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    if (process.env.VERCEL) return [];
    return [{ source: "/api/compute/:path*", destination: `${computeUrl}/api/compute/:path*` }];
  },
};

export default nextConfig;
