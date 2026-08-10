import Link from "next/link";
import { usePathname } from "next/navigation";

export default function MainNav() {
  const pathname = usePathname();

  const linkClass = (href: string) =>
    `px-3 py-1 rounded-md text-sm font-medium ${
      pathname === href
        ? "bg-slate-100 text-slate-900"
        : "text-slate-300 hover:bg-slate-800 hover:text-white"
    }`;

  return (
    <nav className="w-full max-w-2xl mb-6 flex items-center justify-between">
      <span className="text-lg font-semibold">Moodea</span>
      <div className="flex gap-2">
        <Link href="/dashboard" className={linkClass("/dashboard")}>
          Dashboard
        </Link>
        <Link href="/recommendations" className={linkClass("/recommendations")}>
          Recommendations
        </Link>
      </div>
    </nav>
  );
}

