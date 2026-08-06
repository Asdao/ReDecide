import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  images: {
    // Vercel Services currently routes the Next image optimizer endpoint back
    // through the frontend catch-all, where it resolves as an application 404.
    // The source radar and thumbnail assets are already web-ready, so serve
    // them directly instead of depending on /_next/image.
    unoptimized: true,
    remotePatterns: [
      {
        protocol: "https",
        hostname: "raw.githubusercontent.com",
        pathname: "/MurkyYT/cs2-map-icons/main/images/thumbs/**",
      },
    ],
  },
};

export default nextConfig;
