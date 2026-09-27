import { ImageResponse } from "next/og";

export const alt = "SquadMetric — Smarter FPL decisions every gameweek";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    <div
      style={{
        alignItems: "stretch",
        background: "linear-gradient(135deg, #f8fafc 0%, #eef2ff 56%, #ecfdf5 100%)",
        color: "#0f172a",
        display: "flex",
        flexDirection: "column",
        fontFamily: "Arial, sans-serif",
        height: "100%",
        justifyContent: "space-between",
        padding: "68px 76px",
        position: "relative",
        width: "100%",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ alignItems: "center", background: "linear-gradient(135deg, #16a34a, #7c3aed)", borderRadius: 22, color: "white", display: "flex", fontSize: 34, fontWeight: 800, height: 76, justifyContent: "center", width: 76 }}>SM</div>
          <div style={{ fontSize: 40, fontWeight: 800, letterSpacing: "-1.5px" }}>SquadMetric</div>
        </div>
        <div style={{ background: "rgba(255,255,255,0.82)", border: "1px solid #cbd5e1", borderRadius: 999, color: "#166534", display: "flex", fontSize: 20, fontWeight: 700, padding: "12px 22px" }}>Built for FPL managers</div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", maxWidth: 940 }}>
        <div style={{ display: "flex", flexDirection: "column", fontSize: 72, fontWeight: 900, letterSpacing: "-3.5px", lineHeight: 1.02 }}>
          <span>Smarter FPL decisions.</span>
          <span>Every gameweek.</span>
        </div>
        <div style={{ color: "#475569", fontSize: 29, lineHeight: 1.35, marginTop: 26 }}>Rate your squad, understand the weak spots, and see the moves that improve it.</div>
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        {["Squad rating", "Transfers", "Captaincy", "Chip planning"].map((label) => (
          <div key={label} style={{ background: "white", border: "1px solid #cbd5e1", borderRadius: 14, color: "#334155", display: "flex", fontSize: 20, fontWeight: 700, padding: "13px 19px" }}>{label}</div>
        ))}
      </div>
    </div>,
    size,
  );
}
