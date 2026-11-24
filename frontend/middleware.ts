import { NextResponse, type NextRequest } from "next/server";

// When the API is protected by DEEPTERMINAL_API_TOKEN, the web server attaches it to proxied /api
// requests so the token never reaches the browser.
export function middleware(req: NextRequest) {
  const token = process.env.DEEPTERMINAL_API_TOKEN;
  if (!token) return NextResponse.next();
  const headers = new Headers(req.headers);
  headers.set("authorization", `Bearer ${token}`);
  return NextResponse.next({ request: { headers } });
}

export const config = { matcher: "/api/:path*" };
