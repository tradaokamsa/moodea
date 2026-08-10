"use client";

export default function HomePage() {
  const handleLogin = () => {
    window.location.href = "http://localhost:8080/auth/login";
  };

  return (
    <div className="max-w-md w-full text-center space-y-6">
      <h1 className="text-3xl font-bold">Moodea</h1>
      <p className="text-slate-300">
        Discover music based on your mood and listening history.
      </p>
      <button
        onClick={handleLogin}
        className="w-full rounded-md bg-emerald-500 hover:bg-emerald-600 px-4 py-2 font-semibold text-white"
      >
        Login with Spotify
      </button>
    </div>
  );
}

