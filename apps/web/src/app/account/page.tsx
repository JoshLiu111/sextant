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
        <p role="status" className="well mt-6 max-w-[65ch] px-3 py-2 text-sm text-success">
          {t.account.deleted}
        </p>
      )}
      {error && (
        <p role="alert" className="well mt-6 max-w-[65ch] px-3 py-2 text-sm text-error">
          {error}
        </p>
      )}
      {user ? (
        <>
          <p className="mt-6 max-w-[65ch]">
            {t.account.signedInAs} <strong>{user.name || user.email}</strong>
            {user.name && <span className="text-ink-2"> ({user.email})</span>}
          </p>
          <DeleteAccount />
        </>
      ) : (
        <>
          <p className="mt-6 max-w-[65ch] text-ink-2">{t.account.signedOut}</p>
          <SignInLink className="btn btn-primary mt-5" />
        </>
      )}
    </>
  );
}

export default function AccountPage({ searchParams }: PageProps<"/account">) {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 pb-16 pt-10 md:px-6">
      <h1 className="text-3xl">{t.account.heading}</h1>
      <Suspense fallback={null}>
        <AccountBody searchParams={searchParams} />
      </Suspense>
    </main>
  );
}
