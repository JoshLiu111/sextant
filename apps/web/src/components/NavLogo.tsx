import Link from "next/link";
import { Suspense } from "react";
import { getMessages } from "@/i18n";
import { getCurrentUser } from "@/lib/auth/session";

/** The Sextant logo: home is `/dashboard` for signed-in users, `/` for visitors. */
function LogoLink({ href }: { href: "/" | "/dashboard" }) {
  return (
    <Link href={href} className="text-lg font-semibold tracking-tight">
      {getMessages().site.name}
    </Link>
  );
}

async function NavLogoContent() {
  return <LogoLink href={(await getCurrentUser()) ? "/dashboard" : "/"} />;
}

/**
 * The nav logo, pointing at the signed-in user's dashboard or the landing page.
 * Reads the session cookie, so it streams in; until then it points at `/`.
 */
export function NavLogo() {
  return (
    <Suspense fallback={<LogoLink href="/" />}>
      <NavLogoContent />
    </Suspense>
  );
}
