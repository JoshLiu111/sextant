"use client";

import { usePathname } from "next/navigation";
import { getMessages } from "@/i18n";

/** Starts Google sign-in and comes back to the current page afterwards. */
export function SignInLink({ className }: { className?: string }) {
  const t = getMessages();
  const pathname = usePathname();
  const returnTo = pathname === "/account" ? "/" : pathname;
  return (
    // A full navigation (not <Link>): /auth/signin redirects off-site.
    <a href={`/auth/signin?returnTo=${encodeURIComponent(returnTo)}`} className={className}>
      {t.auth.signIn}
    </a>
  );
}
