import React from "react";

const SURFACE_META: Record<string, { label: string; color: string; bg: string }> = {
  clay:        { label: "Clay",        color: "#ea580c", bg: "rgba(234,88,12,0.15)" },
  grass:       { label: "Grass",       color: "#16a34a", bg: "rgba(22,163,74,0.15)" },
  hard:        { label: "Hard",        color: "#2563eb", bg: "rgba(37,99,235,0.15)" },
  indoor_hard: { label: "Indoor Hard", color: "#7c3aed", bg: "rgba(124,58,237,0.15)" },
};

interface Props {
  surface: string;
}

export const SurfaceBadge: React.FC<Props> = ({ surface }) => {
  const meta = SURFACE_META[surface] ?? SURFACE_META.hard;
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: "0.5px",
        padding: "2px 7px",
        borderRadius: 3,
        color: meta.color,
        background: meta.bg,
        whiteSpace: "nowrap",
        textTransform: "uppercase",
      }}
    >
      {meta.label}
    </span>
  );
};
