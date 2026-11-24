import type { NextConfig } from "next";

// Outside Vercel (local dev, CI), proxy browser calls to /api/compute/* to the
// local FastAPI service. On Vercel the top-level rewrite in /vercel.json routes
// /api/compute/* to the compute service before Next.js sees the request.
const computeUrl = process.env.COMPUTE_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  // Under Vercel Services (/vercel.json) every request is rewritten to the web
  // service, where /_next/image doesn't exist (it 404s), so images are served as-is.
  // The landing art is small PNGs sized for their slots.
  images: { unoptimized: true },
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
