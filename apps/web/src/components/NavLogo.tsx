import Image from "next/image";
import Link from "next/link";
import { Suspense } from "react";
import { getMessages } from "@/i18n";
import { getCurrentUser } from "@/lib/auth/session";

/** The Sextant logo: home is `/dashboard` for signed-in users, `/` for visitors. */
function LogoLink({ href }: { href: "/" | "/dashboard" }) {
  return (
    <Link href={href} className="inline-flex items-center gap-2.5 whitespace-nowrap font-display text-2xl leading-none text-ink">
      <Image src="/landing/sextant-assets/brand/favicon-64x64.png" width={32} height={32} alt="" className="size-8 rounded-[7px]" />
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
