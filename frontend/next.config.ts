import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.CIRCUITPILOT_API_URL ?? "http://127.0.0.1:8000"}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: [
      {key: "X-Content-Type-Options", value: "nosniff"},
      {key: "Referrer-Policy", value: "same-origin"},
      {key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=()"},
      {key: "X-Frame-Options", value: "DENY"},
    ] }];
  },
};
export default config;
