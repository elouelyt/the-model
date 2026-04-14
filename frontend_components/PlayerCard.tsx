import React, { useState } from "react";
import { PlayerPrediction } from "./types";

const SIGNAL_META = {
  value_bet: { label: "VALUE BET", color: "#10b981", bg: "rgba(16,185,129,0.10)", border: "#10b981" },
  marginal:  { label: "MARGINAL",  color: "#f59e0b", bg: "rgba(245,158,11,0.10)",  border: "#f59e0b" },
  no_bet:    { label: "NO BET",    color: "#6b7280", bg: "rgba(107,114,128,0.10)", border: "#374151" },
};

const SENTIMENT_STYLE = {
  positive: { color: "#10b981", icon: "↑" },
  concern:  { color: "#f87171", icon: "⚠" },
};

interface Props {
  player: PlayerPrediction;
}

export const PlayerCard: React.FC<Props> = ({ player }) => {
  const [oddsOpen, setOddsOpen] = useState(false);
  const meta = SIGNAL_META[player.signal];
  const edgeSign = player.edge >= 0 ? "+" : "";
  const sent = player.sentiment;
  const sentStyle = sent?.flag && sent.flag in SENTIMENT_STYLE
    ? SENTIMENT_STYLE[sent.flag as keyof typeof SENTIMENT_STYLE]
    : null;

  const bestPrice = player.bookmakers.length
    ? Math.max(...player.bookmakers.map((b) => b.price))
    : null;

  return (
    <div style={{
      background: "#1c1c1c",
      border: "1px solid #262626",
      borderRadius: 8,
      padding: 14,
    }}>
      {/* Name + sentiment */}
      <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>
        {player.player}{" "}
        {sentStyle && sent?.label && (
          <span
            title={sent.headline ?? ""}
            style={{ fontSize: 11, fontWeight: 600, color: sentStyle.color, cursor: "default" }}
          >
            {sentStyle.icon} {sent.label}
          </span>
        )}
      </div>

      {/* Rank / points */}
      <div style={{ fontSize: 11, color: "#737373", marginBottom: 12 }}>
        Rank #{player.rank} · {player.points.toLocaleString()} pts
      </div>

      {/* Stats grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 8,
        marginBottom: 12,
      }}>
        <Stat label="Model" value={`${(player.model_prob * 100).toFixed(1)}%`} />
        <Stat label="Implied" value={`${(player.raw_implied * 100).toFixed(1)}%`} />
        <Stat
          label="Edge"
          value={`${edgeSign}${(player.edge * 100).toFixed(1)}%`}
          valueColor={player.edge > 0 ? "#10b981" : player.edge < -0.02 ? "#f87171" : "#e5e5e5"}
        />
        <Stat label="Vig" value={`${(player.vig_per_player * 100).toFixed(1)}%`} />
      </div>

      {/* Signal badge */}
      <div style={{
        display: "inline-block",
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: "0.5px",
        padding: "3px 10px",
        borderRadius: 4,
        marginBottom: 8,
        color: meta.color,
        background: meta.bg,
        border: `1px solid ${meta.border}`,
      }}>
        {meta.label}
      </div>

      {/* Recommendation */}
      <div style={{ fontSize: 12, color: "#737373", marginBottom: 10 }}>
        {player.recommendation}
      </div>

      {/* Bookmaker odds toggle */}
      {player.bookmakers.length > 0 && (
        <div>
          <button
            onClick={() => setOddsOpen((o) => !o)}
            style={{
              background: "none",
              border: "1px solid #262626",
              borderRadius: 4,
              color: "#737373",
              fontSize: 11,
              padding: "3px 10px",
              cursor: "pointer",
              width: "100%",
              textAlign: "left",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>Odds by bookmaker ({player.bookmakers.length})</span>
            <span>{oddsOpen ? "▲" : "▼"}</span>
          </button>

          {oddsOpen && (
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 6, fontSize: 12 }}>
              <thead>
                <tr>
                  {["Bookmaker", "Price", "Implied"].map((h) => (
                    <th key={h} style={{ textAlign: "left", color: "#525252", fontWeight: 600, padding: "4px 6px", borderBottom: "1px solid #262626" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {player.bookmakers.map((bk) => {
                  const isBest = bestPrice !== null && Math.abs(bk.price - bestPrice) < 0.001;
                  return (
                    <tr key={bk.bookmaker_title}>
                      <td style={{ padding: "4px 6px", color: "#e5e5e5" }}>{bk.bookmaker_title}</td>
                      <td style={{ padding: "4px 6px", color: isBest ? "#10b981" : "#e5e5e5", fontWeight: isBest ? 700 : 400, fontVariantNumeric: "tabular-nums" }}>
                        {bk.price.toFixed(2)}
                      </td>
                      <td style={{ padding: "4px 6px", color: "#737373", fontVariantNumeric: "tabular-nums" }}>
                        {(bk.raw_implied * 100).toFixed(1)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};

const Stat: React.FC<{ label: string; value: string; valueColor?: string }> = ({
  label, value, valueColor = "#e5e5e5",
}) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
    <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.5px", color: "#525252" }}>
      {label}
    </span>
    <span style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums", color: valueColor }}>
      {value}
    </span>
  </div>
);
