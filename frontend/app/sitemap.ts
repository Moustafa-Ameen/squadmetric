import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL?.trim() || "http://localhost:3000").replace(/\/$/, "");
  const publicRoutes = ["", "/onboarding", "/proof", "/privacy", "/terms"];
  return publicRoutes.map((route, index) => ({
    url: `${siteUrl}${route}`,
    changeFrequency: index < 2 ? "weekly" : "monthly",
    priority: index === 0 ? 1 : index === 1 ? 0.9 : 0.6,
  }));
}
