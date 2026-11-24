const backend = process.env.DEEPTERMINAL_BACKEND_URL ?? "http://127.0.0.1:8000";

/** @type {import("next").NextConfig} */
// Plain JavaScript so `next start` needs no TypeScript at runtime (the demo image omits dev dependencies).
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  images: { unoptimized: true },        // no image optimiser endpoint (the UI uses no raster images)
  devIndicators: false,
  // Some analyses take a while on first computation; do not cut the proxied request short.
  experimental: { proxyTimeout: 180_000 },
  async rewrites() {
    // The browser only talks to this origin; the API is proxied server-side.
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "no-referrer" },
        { key: "X-Frame-Options", value: "SAMEORIGIN" },
      ],
    }];
  },
};

export default nextConfig;
