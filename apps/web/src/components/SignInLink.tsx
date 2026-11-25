"use client";

import { usePathname } from "next/navigation";
import { getMessages } from "@/i18n";

/**
 * Starts Google sign-in and comes back to the current page afterwards, or to
 * `returnTo` (a same-site path, e.g. with the page's inputs) when given.
 * When Vercel regenerates the prerendered landing page, usePathname() reads
 * `/index`, which isn't a route, and hydration keeps that href: map it to `/`.
 */
export function SignInLink({ className, returnTo: to }: { className?: string; returnTo?: string }) {
  const t = getMessages();
  const pathname = usePathname();
  const returnTo = to ?? (pathname === "/account" || pathname === "/index" ? "/" : pathname);
  return (
    // A full navigation (not <Link>): /auth/signin redirects off-site.
    <a href={`/auth/signin?returnTo=${encodeURIComponent(returnTo)}`} className={className}>
      {t.auth.signIn}
    </a>
  );
}
