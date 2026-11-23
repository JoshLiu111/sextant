import { SignInLink } from "@/components/SignInLink";
import { getMessages } from "@/i18n";
import { computeFetchAsUser, getCurrentUser, sessionToken } from "@/lib/auth/session";
import type { PortfolioSummary } from "@/lib/portfolios";
import { SavedPortfolios } from "./SavedPortfolios";

async function initialList(): Promise<PortfolioSummary[] | null> {
  const token = await sessionToken();
  if (!token) return null;
  try {
    const res = await computeFetchAsUser(token, "/portfolios", { signal: AbortSignal.timeout(5000) });
    return res.ok ? ((await res.json()) as PortfolioSummary[]) : null;
  } catch {
    return null;
  }
}

/**
 * Saved portfolios for a signed-in user, or a prompt to sign in to save.
 * Reads the session cookie, so render it inside <Suspense>.
 */
export async function SavedPortfoliosSection() {
  const t = getMessages().portfolio;
  const user = await getCurrentUser();
  if (!user) {
    return (
      <div
        data-testid="save-prompt"
        className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-black/10 p-4 text-sm dark:border-white/15"
      >
        <p className="min-w-0 flex-1 text-black/70 dark:text-white/70">{t.savePrompt.body}</p>
        <SignInLink className="rounded-md bg-black px-3 py-1.5 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black" />
      </div>
    );
  }
  return <SavedPortfolios initial={await initialList()} />;
}
