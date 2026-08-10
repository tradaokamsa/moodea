import api from "./api";

export async function getMe() {
  const res = await api.get("/auth/me");
  return res.data;
}

export async function getTopTracks(limit = 10) {
  const res = await api.get("/spotify/top-tracks", {
    params: { time_range: "medium_term", limit },
  });
  return res.data;
}

export async function getRecommendations(limit = 20) {
  const res = await api.post("/recommendations", { limit, context: {} });
  return res.data;
}

export type SimpleTrack = {
  id: string;
  name: string;
  artists: string[];
};

export async function getTracksByIds(ids: string[]): Promise<SimpleTrack[]> {
  if (ids.length === 0) return [];
  const res = await api.get("/spotify/tracks", {
    params: { ids: ids.join(",") },
  });
  return res.data;
}

export async function postInteraction(opts: {
  track_id: string;
  interaction_type: "like" | "skip" | "continue";
  score: number;
}) {
  const res = await api.post("/interactions", {
    ...opts,
    session_id: "default",
    context: {},
  });
  return res.data;
}

