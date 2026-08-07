import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The documented local URLs use both hostnames. Without this, opening the
  // dev server through 127.0.0.1 can block Next's client/HMR resources and
  // leave a server-rendered page that appears but is not reliably interactive.
  allowedDevOrigins: ["127.0.0.1"],
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
