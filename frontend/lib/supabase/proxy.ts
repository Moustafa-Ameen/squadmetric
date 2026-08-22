import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { sanitizeNextPath } from "@/lib/auth";
import { getSupabasePublicConfig } from "./config";

const PUBLIC_PATHS = new Set([
  "/",
  "/login",
  "/signup",
  "/forgot-password",
  "/auth/callback",
  "/auth/confirm",
  "/auth/error",
  "/privacy",
  "/terms",
]);
const AUTH_PATHS = new Set(["/login", "/signup", "/forgot-password"]);

export async function updateSupabaseSession(request: NextRequest) {
  const config = getSupabasePublicConfig();
  if (!config) return NextResponse.next();

  let response = NextResponse.next({ request });
  const supabase = createServerClient(config.url, config.publishableKey, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });

  const { data, error } = await supabase.auth.getClaims();
  const authenticated = !error && Boolean(data?.claims?.sub);
  const path = request.nextUrl.pathname;
  const isPublic = PUBLIC_PATHS.has(path);

  if (!authenticated && !isPublic) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.search = "";
    loginUrl.searchParams.set("next", sanitizeNextPath(`${path}${request.nextUrl.search}`, "/dashboard"));
    return NextResponse.redirect(loginUrl);
  }

  if (authenticated && AUTH_PATHS.has(path)) {
    const next = sanitizeNextPath(request.nextUrl.searchParams.get("next"), "/dashboard");
    return NextResponse.redirect(new URL(next, request.url));
  }

  return response;
}
