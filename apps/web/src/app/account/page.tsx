import type { Metadata } from "next";
import { Suspense } from "react";
import { DeleteAccount } from "@/components/DeleteAccount";
import { SignInLink } from "@/components/SignInLink";
import { getMessages } from "@/i18n";
import { getCurrentUser } from "@/lib/auth/session";

const t = getMessages();

export const metadata: Metadata = { title: t.account.heading };

type ErrorKey = keyof typeof t.account.errors;

async function AccountBody({ searchParams }: { searchParams: PageProps<"/account">["searchParams"] }) {
  const params = await searchParams;
  const error = typeof params.error === "string" && params.error in t.account.errors
    ? t.account.errors[params.error as ErrorKey]
    : null;
  const user = await getCurrentUser();

  return (
    <>
      {params.deleted === "1" && !user && (
        <p role="status" className="mt-4 rounded bg-green-100 px-3 py-2 text-sm text-green-900">
          {t.account.deleted}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-4 rounded bg-red-100 px-3 py-2 text-sm text-red-900">
          {error}
        </p>
      )}
      {user ? (
        <>
          <p className="mt-4">
            {t.account.signedInAs} <strong>{user.name || user.email}</strong>
            {user.name && <span className="text-black/70 dark:text-white/70"> ({user.email})</span>}
          </p>
          <DeleteAccount />
        </>
      ) : (
        <>
          <p className="mt-4 text-black/70 dark:text-white/70">{t.account.signedOut}</p>
          <SignInLink className="mt-4 inline-block rounded border border-black/15 px-3 py-1.5 hover:underline dark:border-white/20" />
        </>
      )}
    </>
  );
}

export default function AccountPage({ searchParams }: PageProps<"/account">) {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.account.heading}</h1>
      <Suspense fallback={null}>
        <AccountBody searchParams={searchParams} />
      </Suspense>
    </main>
  );
}
