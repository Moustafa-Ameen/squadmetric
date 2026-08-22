export function sanitizeNextPath(value: string | null | undefined, fallback = "/dashboard"): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return fallback;

  try {
    const parsed = new URL(value, "https://squadmetric.local");
    if (parsed.origin !== "https://squadmetric.local") return fallback;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
}

export function authRedirectUrl(path: string): string {
  if (typeof window !== "undefined") return `${window.location.origin}${path}`;

  const configured = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  if (configured) return `${configured.replace(/\/$/, "")}${path}`;

  return `http://localhost:3000${path}`;
}
