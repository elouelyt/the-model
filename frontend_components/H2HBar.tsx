import React from "react";
import { H2HResult } from "./types";

const SURFACE_LABELS: Record<string, string> = {
  clay: "Clay", grass: "Grass", hard: "Hard", indoor_hard: "Indoor Hard",
};

interface Props {
  h2h: H2HResult | null;
  home: string;
  away: string;
  surface: string;
}

export const H2HBar: React.FC<Props> = ({ h2h, home, away, surface }) => {
  if (!h2h?.available) return null;

  const homeShort = home.split(" ").at(-1)!;
  const awayShort = away.split(" ").at(-1)!;
  const surfLabel = SURFACE_LABELS[surface] ?? surface;

  const leaderStyle = { color: "#E8650A", fontWeight: 700 };
  const trailerStyle = { color: "#737373", fontWeight: 500 };
  const neutralStyle = { color: "#e5e5e5", fontWeight: 500 };

  // ── No history ────────────────────────────────────────────────────────────
  if (h2h.total === 0) {
    return (
      <div style={barStyle}>
        <Tag>H2H</Tag>
        <span style={{ color: "#525252", fontStyle: "italic", fontSize: 12 }}>
          No previous meetings (last 4 years)
        </span>
      </div>
    );
  }

  // ── Overall record ────────────────────────────────────────────────────────
  const aStyle = h2h.leader === "a" ? leaderStyle : h2h.leader === "b" ? trailerStyle : neutralStyle;
  const bStyle = h2h.leader === "b" ? leaderStyle : h2h.leader === "a" ? trailerStyle : neutralStyle;

  return (
    <div style={barStyle}>
      <Tag>H2H</Tag>

      {/* Overall */}
      <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
        <span style={aStyle}>{homeShort} {h2h.a_wins}</span>
        <span style={{ color: "#525252" }}>–</span>
        <span style={bStyle}>{h2h.b_wins} {awayShort}</span>
        <span style={{ color: "#525252", fontSize: 11, marginLeft: 2 }}>
          ({h2h.total} match{h2h.total !== 1 ? "es" : ""})
        </span>
      </span>

      {/* Surface breakdown */}
      {h2h.total_surface > 0 && (() => {
        const asStyle = h2h.leader_surface === "a" ? leaderStyle : h2h.leader_surface === "b" ? trailerStyle : neutralStyle;
        const bsStyle = h2h.leader_surface === "b" ? leaderStyle : h2h.leader_surface === "a" ? trailerStyle : neutralStyle;
        return (
          <>
            <span style={{ color: "#262626" }}>·</span>
            <span style={{ color: "#737373", fontSize: 12 }}>{surfLabel}:</span>
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <span style={asStyle}>{homeShort} {h2h.a_wins_surface}</span>
              <span style={{ color: "#525252" }}>–</span>
              <span style={bsStyle}>{h2h.b_wins_surface} {awayShort}</span>
              <span style={{ color: "#525252", fontSize: 11, marginLeft: 2 }}>
                ({h2h.total_surface})
              </span>
            </span>
          </>
        );
      })()}
    </div>
  );
};

const barStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  flexWrap: "wrap",
  gap: 6,
  padding: "7px 12px",
  marginBottom: 12,
  background: "#1c1c1c",
  border: "1px solid #262626",
  borderRadius: 6,
  fontSize: 12,
  fontVariantNumeric: "tabular-nums",
};

const Tag: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span style={{
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "0.5px",
    color: "#525252",
    textTransform: "uppercase",
    marginRight: 2,
  }}>
    {children}
  </span>
);
