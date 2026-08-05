import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  images: {
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
