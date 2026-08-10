"use client";

import { useEffect, useState } from "react";
import {
  getRecommendations,
  getTracksByIds,
  type SimpleTrack,
  postInteraction,
} from "@/lib/endpoints";
import MainNav from "@/components/MainNav";

type RecommendationsResponse = {
  track_ids: string[];
  scores: number[];
};

type TrackMap = Record<string, SimpleTrack>;

export default function RecommendationsPage() {
  const [recs, setRecs] = useState<RecommendationsResponse | null>(null);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [trackMap, setTrackMap] = useState<TrackMap>({});

  async function loadRecs() {
    setLoading(true);
    try {
      const data = (await getRecommendations(20)) as RecommendationsResponse;
      setRecs(data);
      setIndex(0);

      // Fetch metadata for these tracks so we can show names/artists
      const meta = await getTracksByIds(data.track_ids);
      const map: TrackMap = {};
      for (const t of meta) {
        map[t.id] = t;
      }
      setTrackMap(map);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRecs();
  }, []);

  if (loading) return <div>Loading recommendations...</div>;
  if (!recs || recs.track_ids.length === 0) {
    return (
      <div className="max-w-md w-full space-y-4 text-center">
        <MainNav />
        <p>No recommendations yet. Try listening and interacting more.</p>
        <button
          onClick={loadRecs}
          className="rounded-md bg-slate-800 px-4 py-2 text-sm"
        >
          Refresh
        </button>
      </div>
    );
  }

  const currentId = recs.track_ids[index];
  const currentScore = recs.scores[index];
  const meta = trackMap[currentId];

  async function handleAction(
    interaction_type: "like" | "skip" | "continue",
    score: number
  ) {
    if (!currentId || !recs) return;
    await postInteraction({ track_id: currentId, interaction_type, score });
    if (index + 1 < recs.track_ids.length) {
      setIndex(index + 1);
    } else {
      await loadRecs();
    }
  }

  return (
    <div className="max-w-md w-full space-y-6 text-center">
      <MainNav />
      <h1 className="text-2xl font-bold">Recommendations</h1>
      <div className="rounded-lg bg-slate-900 px-4 py-6 space-y-2">
        <p className="text-sm text-slate-400">
          {meta && meta.name ? "Track" : "Track ID"}
        </p>
        <p className="font-semibold text-lg">
          {meta && meta.name ? meta.name : currentId}
        </p>
        {meta && meta.artists && meta.artists.length > 0 && (
          <p className="text-xs text-slate-400">
            {meta.artists.join(", ")}
          </p>
        )}
        <p className="text-xs text-slate-500">
          Score: {currentScore.toFixed(3)}
        </p>
      </div>
      <div className="flex justify-between gap-2">
        <button
          onClick={() => handleAction("skip", -1)}
          className="flex-1 rounded-md bg-red-600 hover:bg-red-700 px-3 py-2 text-sm font-semibold"
        >
          Skip
        </button>
        <button
          onClick={() => handleAction("continue", 1)}
          className="flex-1 rounded-md bg-amber-500 hover:bg-amber-600 px-3 py-2 text-sm font-semibold"
        >
          Continue
        </button>
        <button
          onClick={() => handleAction("like", 3)}
          className="flex-1 rounded-md bg-emerald-500 hover:bg-emerald-600 px-3 py-2 text-sm font-semibold"
        >
          Like
        </button>
      </div>
    </div>
  );
}

