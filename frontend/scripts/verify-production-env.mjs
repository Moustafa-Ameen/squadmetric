const required = [
  "FPL_API_SERVER_URL",
  "NEXT_PUBLIC_SUPABASE_URL",
  "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
  "SUPABASE_SERVICE_ROLE_KEY",
  "NEXT_PUBLIC_SITE_URL",
  "NEXT_PUBLIC_SUPPORT_EMAIL",
];

const missing = required.filter((name) => !process.env[name]?.trim());
if (missing.length) fail(`Missing production environment variables: ${missing.join(", ")}`);

const apiUrl = absoluteUrl("FPL_API_SERVER_URL");
const supabaseUrl = absoluteUrl("NEXT_PUBLIC_SUPABASE_URL");
const siteUrl = absoluteUrl("NEXT_PUBLIC_SITE_URL");
const localHosts = new Set(["localhost", "127.0.0.1", "::1"]);

if (localHosts.has(apiUrl.hostname) && process.env.FPL_ALLOW_LOCAL_API !== "true") {
  fail("A production deployment cannot target a loopback API unless FPL_ALLOW_LOCAL_API=true.");
}
if (supabaseUrl.protocol !== "https:") fail("NEXT_PUBLIC_SUPABASE_URL must use https.");
if (siteUrl.protocol !== "https:") fail("NEXT_PUBLIC_SITE_URL must use https.");
if (siteUrl.pathname !== "/" || siteUrl.search || siteUrl.hash) fail("NEXT_PUBLIC_SITE_URL must be a canonical origin without a path, query, or fragment.");
if (!/^\S+@\S+\.\S+$/.test(process.env.NEXT_PUBLIC_SUPPORT_EMAIL)) fail("NEXT_PUBLIC_SUPPORT_EMAIL must be a valid public support address.");

console.log(`Production contract verified for ${siteUrl.origin}. API: ${apiUrl.origin}. Supabase: ${supabaseUrl.origin}.`);

function absoluteUrl(name) {
  try {
    const value = new URL(process.env[name]);
    if (!["http:", "https:"].includes(value.protocol)) throw new Error("unsupported protocol");
    return value;
  } catch {
    fail(`${name} must be an absolute http(s) URL.`);
  }
}

function fail(message) {
  console.error(message);
  process.exit(1);
}
