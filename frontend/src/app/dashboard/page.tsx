"use client";

import { useEffect, useState } from "react";
import { getMe, getTopTracks } from "@/lib/endpoints";
import MainNav from "@/components/MainNav";

type User = { id: string; display_name: string };

type Track = {
  id: string;
  name: string;
  artists?: { name: string }[];
};

export default function DashboardPage() {
  const [user, setUser] = useState<User | null>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const me = await getMe();
        setUser(me);

        const top = await getTopTracks(10);
        const items = (top as any).items || (top as any).tracks || [];
        setTracks(items);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (!user) return <div>Not logged in.</div>;

  return (
    <div className="max-w-2xl w-full space-y-4">
      <MainNav />
      <h1 className="text-2xl font-bold">Welcome, {user.display_name}</h1>
      <h2 className="text-lg font-semibold mt-4">Your top tracks</h2>
      <ul className="space-y-2">
        {tracks.map((t) => (
          <li
            key={t.id}
            className="flex flex-col rounded-md bg-slate-900 px-3 py-2"
          >
            <span className="font-medium">{t.name}</span>
            <span className="text-xs text-slate-400">
              {t.artists?.map((a) => a.name).join(", ")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

