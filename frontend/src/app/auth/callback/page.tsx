"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function AuthCallbackInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const token = searchParams.get("token");
    if (token) {
      try {
        window.localStorage.setItem("moodea_jwt", token);
      } catch (e) {
        console.error("Failed to store token", e);
      }
      router.replace("/dashboard");
    }
  }, [router, searchParams]);

  return <div>Finishing login…</div>;
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<div>Finishing login…</div>}>
      <AuthCallbackInner />
    </Suspense>
  );
}


