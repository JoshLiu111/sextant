import Link from "next/link";
import { Suspense } from "react";
import { getMessages } from "@/i18n";
import { getCurrentUser } from "@/lib/auth/session";
import { SignInLink } from "./SignInLink";

async function AccountMenuContent() {
  const t = getMessages();
  const user = await getCurrentUser();
  const settings = (
    <Link href="/settings" className="whitespace-nowrap rounded-card px-2 py-2 text-sm text-ink-2 hover:bg-paper-2 hover:text-ink">
      {t.auth.settings}
    </Link>
  );
  if (!user) {
    return (
      <div className="flex items-center gap-2">
        {settings}
        <SignInLink className="btn btn-sm" />
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-x-1 gap-y-1 text-sm">
      <Link href="/dashboard" className="whitespace-nowrap rounded-card px-2 py-2 font-medium text-ink hover:bg-paper-2">
        {t.auth.dashboard}
      </Link>
      <span data-testid="signed-in-user" className="max-w-40 truncate text-muted">
        {user.name || user.email}
      </span>
      {settings}
      <Link href="/account" className="cursor-pointer whitespace-nowrap rounded-card px-2 py-2 text-ink-2 hover:bg-paper-2 hover:text-ink">
        {t.auth.account}
      </Link>
      <form method="post" action="/auth/signout">
        <button type="submit" className="cursor-pointer whitespace-nowrap rounded-card px-2 py-2 text-ink-2 hover:bg-paper-2 hover:text-ink">
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
