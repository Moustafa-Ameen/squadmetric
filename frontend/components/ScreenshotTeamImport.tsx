"use client";

import { ImagePlus, LoaderCircle, Search, Upload, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { getPlayerCatalog, getProvisionalTeamRating } from "@/lib/api";
import { detectPlayersFromOcr, normalizePlayerName } from "@/lib/screenshotTeam";
import type { Player, ScreenshotAnalysis } from "@/lib/types";

export function ScreenshotTeamImport({
  onAnalyzed,
}: {
  onAnalyzed: (analysis: ScreenshotAnalysis) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [catalog, setCatalog] = useState<Player[]>([]);
  const [players, setPlayers] = useState<Player[]>([]);
  const [query, setQuery] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [bank, setBank] = useState(0);
  const [freeTransfers, setFreeTransfers] = useState(1);
  const [error, setError] = useState("");

  const results = useMemo(() => {
    const needle = normalizePlayerName(query);
    if (!needle) return [];
    const selected = new Set(players.map((player) => Number(player.element_id)));
    return catalog
      .filter((player) => !selected.has(Number(player.element_id)))
      .filter((player) => normalizePlayerName(`${player.web_name ?? ""} ${player.name}`).includes(needle))
      .slice(0, 6);
  }, [catalog, players, query]);

  async function readScreenshot(file: File) {
    setError("");
    setPlayers([]);
    setProgress(0);
    try {
      const [{ recognize }, playerCatalog] = await Promise.all([
        import("tesseract.js"),
        getPlayerCatalog(1000),
      ]);
      setCatalog(playerCatalog);
      const result = await recognize(file, "eng", {
        workerPath: "/tesseract/worker.min.js",
        corePath: "/tesseract/tesseract-core-simd-lstm.wasm.js",
        langPath: "/tesseract/lang",
        logger: (message) => {
          if (message.status === "recognizing text") setProgress(Math.round((message.progress ?? 0) * 100));
        },
      });
      const detected = detectPlayersFromOcr(result.data.text, playerCatalog);
      setPlayers(detected);
      if (detected.length < 15) {
        setError(`We found ${detected.length} of 15 players. Search below to add anything the screenshot missed.`);
      }
    } catch {
      setError("We could not read that image. Try a clearer full-squad screenshot or add the players manually.");
    } finally {
      setProgress(null);
    }
  }

  async function analyze() {
    if (players.length !== 15 || analyzing) return;
    setAnalyzing(true);
    setError("");
    try {
      const elementIds = players.map((player) => Number(player.element_id));
      const decision = await getProvisionalTeamRating({
        element_ids: elementIds,
        bank,
        free_transfers: freeTransfers,
      });
      onAnalyzed({ decision, elementIds, bank, freeTransfers });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The provisional rating could not be calculated.");
    } finally {
      setAnalyzing(false);
    }
  }

  function addPlayer(player: Player) {
    if (players.length >= 15) return;
    setPlayers((current) => [...current, player]);
    setQuery("");
    setError("");
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-violet-700 shadow-sm"><ImagePlus className="h-5 w-5" /></span>
        <div>
          <h3 className="font-black text-slate-950">Use a team screenshot</h3>
          <p className="mt-1 text-xs leading-5 text-slate-600">Private, browser-based text recognition. The result is provisional because screenshots do not include exact selling prices.</p>
        </div>
      </div>
      <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={(event) => { const file = event.target.files?.[0]; if (file) void readScreenshot(file); }} />
      <button type="button" onClick={() => inputRef.current?.click()} disabled={progress !== null} className="sm-secondary-button mt-4 w-full justify-center px-4 py-3">
        {progress !== null ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
        {progress !== null ? `Reading screenshot${progress ? ` · ${progress}%` : "…"}` : "Choose screenshot"}
      </button>

      {catalog.length > 0 ? (
        <div className="mt-4">
          <div className="flex items-center justify-between gap-3"><label htmlFor="screenshot-player-search" className="text-xs font-bold text-slate-700">Detected squad</label><span className={`text-xs font-black ${players.length === 15 ? "text-emerald-700" : "text-amber-700"}`}>{players.length}/15</span></div>
          <div className="mt-2 flex flex-wrap gap-2">{players.map((player) => <span key={player.element_id} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700">{player.web_name || player.name}<button type="button" aria-label={`Remove ${player.web_name || player.name}`} onClick={() => setPlayers((current) => current.filter((item) => item.element_id !== player.element_id))}><X className="h-3 w-3 text-slate-400" /></button></span>)}</div>
          {players.length < 15 ? <div className="relative mt-3"><Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" /><input id="screenshot-player-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Add a missing player" className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-9 pr-3 text-sm outline-none focus:border-violet-500 focus:ring-4 focus:ring-violet-100" />{results.length ? <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">{results.map((player) => <button key={player.element_id} type="button" onClick={() => addPlayer(player)} className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm hover:bg-violet-50"><span className="font-semibold text-slate-900">{player.web_name || player.name}</span><span className="text-xs text-slate-500">{player.team} · {player.position}</span></button>)}</div> : null}</div> : null}
          <div className="mt-4 grid grid-cols-2 gap-3"><label className="text-xs font-bold text-slate-700">Bank (£m)<input type="number" min="0" max="20" step="0.1" value={bank} onChange={(event) => setBank(Number(event.target.value))} className="mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm" /></label><label className="text-xs font-bold text-slate-700">Free transfers<select value={freeTransfers} onChange={(event) => setFreeTransfers(Number(event.target.value))} className="mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm">{[0, 1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value}</option>)}</select></label></div>
          <button type="button" onClick={() => void analyze()} disabled={players.length !== 15 || analyzing} className="sm-primary-button mt-4 w-full justify-center px-4 py-3 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none">{analyzing ? <><LoaderCircle className="h-4 w-4 animate-spin" />Rating squad…</> : "Rate this squad"}</button>
        </div>
      ) : null}
      {error ? <p className="mt-3 text-xs leading-5 text-rose-700" role="alert">{error}</p> : null}
    </div>
  );
}
