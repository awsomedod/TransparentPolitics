import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // During local development, proxy /api/* to the FastAPI backend at :8000.
  // This means frontend code always calls relative URLs like /api/v1/health —
  // no hardcoded backend URLs, no CORS configuration needed in the browser.
  // In production, Nginx handles this routing instead.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
