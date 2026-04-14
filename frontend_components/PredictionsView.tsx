/**
 * PredictionsView — top-level component.
 *
 * Drop this into your Lovable project as a replacement for the current
 * predictions page / main view. It handles fetching, loading, empty, and
 * error states, then renders a MatchCard per prediction.
 *
 * Required env var in Lovable:  VITE_API_KEY  (your TENNIS_API_KEY value)
 * API endpoint constant below:  API_URL       (update if gateway URL changes)
 */

import React, { useState } from "react";
import { PredictResponse } from "./types";
import { MatchCard } from "./MatchCard";

const API_URL = "https://tennis-gateway-agmlnd9p.uc.gateway.dev/predict";
const API_KEY = import.meta.env.VITE_API_KEY as string;

type Status = "idle" | "loading" | "success" | "error";

export const PredictionsView: React.FC = () => {
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<PredictResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");

  const runPipeline = async () => {
    setStatus("loading");
    setErrorMsg("");
    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": API_KEY,
        },
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`${res.status} — ${body}`);
      }
      const json: PredictResponse = await res.json();
      setData(json);
      setStatus("success");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  };

  return (
    <div style={{ background: "#0a0a0a", minHeight: "100vh", color: "#e5e5e5", fontFamily: "system-ui, sans-serif" }}>
      {/* Header */}
      <header style={{
        borderBottom: "1px solid #262626",
        padding: "20px 24px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
      }}>
        <span style={{ fontSize: 18, fontWeight: 700, letterSpacing: "-0.3px" }}>
          The <span style={{ color: "#E8650A" }}>Model</span>
        </span>
        <span style={{ fontSize: 12, color: "#737373" }}>
          ATP · Pre-match predictions
        </span>
      </header>

      {/* Main */}
      <main style={{ maxWidth: 860, margin: "0 auto", padding: "24px 16px 48px" }}>

        {/* Run button */}
        <div style={{ marginBottom: 24, display: "flex", alignItems: "center", gap: 16 }}>
          <button
            onClick={runPipeline}
            disabled={status === "loading"}
            style={{
              background: status === "loading" ? "#333" : "#E8650A",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              padding: "10px 22px",
              fontSize: 14,
              fontWeight: 600,
              cursor: status === "loading" ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              gap: 8,
              transition: "background 0.15s",
            }}
          >
            {status === "loading" ? (
              <><Spinner /> Running pipeline…</>
            ) : (
              "▶  Run predictions"
            )}
          </button>

          {status === "success" && data && (
            <span style={{ fontSize: 13, color: "#737373" }}>
              <strong style={{ color: "#e5e5e5" }}>{data.matches_total}</strong> match{data.matches_total !== 1 ? "es" : ""}
              {" · "}
              <strong style={{ color: "#10b981" }}>
                {data.predictions.flatMap((m) => m.players ?? []).filter((p) => p.signal === "value_bet").length}
              </strong>{" "}
              value bet{data.predictions.flatMap((m) => m.players ?? []).filter((p) => p.signal === "value_bet").length !== 1 ? "s" : ""} found
              {" · "}
              <span style={{ color: "#525252" }}>{new Date(data.fetched_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })} UTC</span>
            </span>
          )}
        </div>

        {/* States */}
        {status === "idle" && (
          <EmptyState
            icon="○"
            title="No predictions loaded"
            body="Click "Run predictions" to fetch live ATP pre-match odds and compute value signals."
          />
        )}

        {status === "error" && (
          <EmptyState
            icon="✕"
            title="Pipeline error"
            body={errorMsg}
            accent="#ef4444"
          />
        )}

        {status === "success" && data && data.predictions.length === 0 && (
          <EmptyState
            icon="○"
            title="No pre-match matches right now"
            body="All current matches are in-play, or no ATP tournament is active. Try again later."
          />
        )}

        {status === "success" && data && data.predictions.map((match, i) => (
          <MatchCard key={`${match.home}-${match.away}-${i}`} match={match} />
        ))}
      </main>
    </div>
  );
};

// ── Helpers ────────────────────────────────────────────────────────────────

const Spinner: React.FC = () => (
  <span style={{
    display: "inline-block",
    width: 14,
    height: 14,
    border: "2px solid rgba(255,255,255,0.3)",
    borderTopColor: "#fff",
    borderRadius: "50%",
    animation: "spin 0.7s linear infinite",
  }} />
);

const EmptyState: React.FC<{
  icon: string;
  title: string;
  body: string;
  accent?: string;
}> = ({ icon, title, body, accent = "#E8650A" }) => (
  <div style={{
    textAlign: "center",
    padding: "48px 24px",
    border: `1px solid ${accent}33`,
    borderRadius: 10,
    background: "#141414",
  }}>
    <div style={{ fontSize: 32, color: accent, marginBottom: 12 }}>{icon}</div>
    <div style={{ fontSize: 16, fontWeight: 600, color: "#e5e5e5", marginBottom: 8 }}>{title}</div>
    <div style={{ fontSize: 13, color: "#737373", maxWidth: 400, margin: "0 auto" }}>{body}</div>
  </div>
);
