import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse } from "next/server";
import { sanitizeNextPath } from "@/lib/auth";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");
  const type = url.searchParams.get("type") as EmailOtpType | null;
  const next = sanitizeNextPath(url.searchParams.get("next"), "/dashboard");
  const supabase = await createSupabaseServerClient();

  if (supabase && (code || (tokenHash && type))) {
    const { error } = code
      ? await supabase.auth.exchangeCodeForSession(code)
      : await supabase.auth.verifyOtp({ token_hash: tokenHash!, type: type! });
    if (!error) {
      const forwardedHost = request.headers.get("x-forwarded-host");
      const forwardedProto = request.headers.get("x-forwarded-proto") ?? "https";
      if (process.env.NODE_ENV !== "development" && forwardedHost) {
        return noStoreRedirect(`${forwardedProto}://${forwardedHost}${next}`);
      }
      return noStoreRedirect(`${url.origin}${next}`);
    }
  }

  return noStoreRedirect(`${url.origin}/auth/error`);
}

function noStoreRedirect(url: string) {
  const response = NextResponse.redirect(url);
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}
