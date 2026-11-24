import Link from "next/link";
import { Suspense } from "react";
import { getMessages } from "@/i18n";
import { getCurrentUser } from "@/lib/auth/session";
import { SignInLink } from "./SignInLink";

async function AccountMenuContent() {
  const t = getMessages();
  const user = await getCurrentUser();
  const settings = (
    <Link href="/settings" className="text-sm hover:underline">
      {t.auth.settings}
    </Link>
  );
  if (!user) {
    return (
      <div className="flex items-center gap-3">
        {settings}
        <SignInLink className="rounded border border-black/15 px-3 py-1 text-sm hover:underline dark:border-white/20" />
      </div>
    );
  }
  return (
    <div className="flex items-center gap-3 text-sm">
      <Link href="/dashboard" className="font-medium hover:underline">
        {t.auth.dashboard}
      </Link>
      <span data-testid="signed-in-user" className="max-w-40 truncate font-medium">
        {user.name || user.email}
      </span>
      {settings}
      <Link href="/account" className="hover:underline">
        {t.auth.account}
      </Link>
      <form method="post" action="/auth/signout">
        <button type="submit" className="hover:underline">
          {t.auth.signOut}
        </button>
      </form>
    </div>
  );
}

/** Signed-in state for the nav. Reads the session cookie, so it streams in. */
export function AccountMenu() {
  return (
    <Suspense fallback={<span className="text-sm" aria-hidden />}>
      <AccountMenuContent />
    </Suspense>
  );
}
