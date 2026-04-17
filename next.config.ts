import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Edge routing to Flask handles python backend in Vercel.
  // Next.js rewrites are omitted since they hide original paths from Vercel Python builder.
};

export default nextConfig;
