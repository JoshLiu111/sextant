import type { Metadata } from "next";
import { Suspense } from "react";
import { SignInLink } from "@/components/SignInLink";
import { getMessages } from "@/i18n";
import { computeFetchAsUser, getCurrentUser, sessionToken } from "@/lib/auth/session";
import { PROVIDERS, type SavedKey } from "@/lib/providerKeys";
import { ProviderKeySettings } from "./ProviderKeySettings";

const t = getMessages();

export const metadata: Metadata = { title: t.settings.heading };

/** The user's saved keys (hints only); empty if none or the list failed to load. */
async function savedKeys(): Promise<SavedKey[]> {
  const token = await sessionToken();
  if (!token) return [];
  try {
    const res = await computeFetchAsUser(token, "/keys", { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return [];
    return (await res.json()) as SavedKey[];
  } catch {
    return [];
  }
}

/** Reads the session cookie, so it renders inside <Suspense>. */
async function SettingsBody() {
  const user = await getCurrentUser();
  if (!user) {
    return (
      <div
        data-testid="key-sign-in-prompt"
        className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-black/10 p-4 text-sm dark:border-white/15"
      >
        <p className="min-w-0 flex-1 text-black/70 dark:text-white/70">{t.settings.signInPrompt}</p>
        <SignInLink className="rounded-md bg-black px-3 py-1.5 font-medium text-white hover:bg-black/80 dark:bg-white dark:text-black" />
      </div>
    );
  }
  const keys = await savedKeys();
  return PROVIDERS.map((provider) => (
    <ProviderKeySettings
      key={provider}
      provider={provider}
      initial={keys.find((k) => k.provider === provider) ?? null}
    />
  ));
}

export default function SettingsPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.settings.heading}</h1>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.settings.intro}</p>
      <Suspense fallback={null}>
        <SettingsBody />
      </Suspense>
    </main>
  );
}
