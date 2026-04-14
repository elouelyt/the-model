import React from "react";
import { MatchPrediction } from "./types";
import { SurfaceBadge } from "./SurfaceBadge";
import { H2HBar } from "./H2HBar";
import { PlayerCard } from "./PlayerCard";

interface Props {
  match: MatchPrediction;
}

export const MatchCard: React.FC<Props> = ({ match }) => {
  const commenceDate = new Date(match.commence_time);
  const timeStr = commenceDate.toLocaleString("en-GB", {
    weekday: "short", day: "2-digit", month: "short",
    hour: "2-digit", minute: "2-digit", timeZone: "UTC",
  }) + " UTC";

  // Border accent colour driven by best signal
  const signals = match.players?.map((p) => p.signal) ?? [];
  const accent = signals.includes("value_bet")
    ? "#10b981"
    : signals.includes("marginal")
    ? "#f59e0b"
    : "#2a2a2a";

  // ── Error card ─────────────────────────────────────────────────────────────
  if (match.error) {
    return (
      <div style={{ ...cardBase, borderLeft: "3px solid #ef4444" }}>
        <MatchHeader match={match} timeStr={timeStr} />
        <div style={{ fontSize: 13, color: "#f87171", marginTop: 8 }}>
          ⚠ {match.error}
        </div>
      </div>
    );
  }

  return (
    <div style={{ ...cardBase, borderLeft: `3px solid ${accent}` }}>
      <MatchHeader match={match} timeStr={timeStr} />

      <H2HBar
        h2h={match.h2h}
        home={match.home}
        away={match.away}
        surface={match.surface}
      />

      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 12,
      }}>
        {match.players?.map((p) => (
          <PlayerCard key={p.player} player={p} />
        ))}
      </div>
    </div>
  );
};

// ── Sub-components ─────────────────────────────────────────────────────────

const MatchHeader: React.FC<{ match: MatchPrediction; timeStr: string }> = ({ match, timeStr }) => (
  <div style={{
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: 12,
    marginBottom: 16,
  }}>
    <span style={{ fontSize: 16, fontWeight: 600, color: "#e5e5e5" }}>
      {match.home}{" "}
      <span style={{ color: "#737373", fontWeight: 400, margin: "0 4px" }}>vs</span>{" "}
      {match.away}
    </span>
    <span style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
      <SurfaceBadge surface={match.surface} />
      <span style={{ fontSize: 12, color: "#737373", whiteSpace: "nowrap" }}>{timeStr}</span>
    </span>
  </div>
);

const cardBase: React.CSSProperties = {
  background: "#141414",
  border: "1px solid #262626",
  borderRadius: 10,
  padding: 20,
  marginBottom: 16,
};
