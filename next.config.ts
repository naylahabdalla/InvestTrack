import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return {
      fallback: [
        {
          source: '/:path*',
          destination: '/api/index.py',
        },
      ],
    };
  },
};

export default nextConfig;
