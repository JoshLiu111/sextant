"use client";

import { useState } from "react";
import { getMessages } from "@/i18n";

/** Two-step delete: nothing is sent until the user confirms. */
export function DeleteAccount() {
  const t = getMessages().account.delete;
  const [confirming, setConfirming] = useState(false);

  return (
    <section className="mt-10 rounded-lg border border-red-300 p-4 dark:border-red-800">
      <h2 className="font-semibold">{t.heading}</h2>
      <p className="mt-1 text-sm text-black/70 dark:text-white/70">{t.body}</p>
      {confirming ? (
        <form method="post" action="/account/delete" className="mt-4 flex flex-wrap items-center gap-3">
          <p role="alert" className="w-full text-sm font-medium text-red-700 dark:text-red-400">
            {t.warning}
          </p>
          <button type="submit" className="rounded bg-red-700 px-3 py-1.5 text-sm font-medium text-white">
            {t.confirm}
          </button>
          <button
            type="button"
            className="rounded border border-black/15 px-3 py-1.5 text-sm dark:border-white/20"
            onClick={() => setConfirming(false)}
          >
            {t.cancel}
          </button>
        </form>
      ) : (
        <button
          type="button"
          className="mt-4 rounded border border-red-700 px-3 py-1.5 text-sm font-medium text-red-700 dark:text-red-400"
          onClick={() => setConfirming(true)}
        >
          {t.button}
        </button>
      )}
    </section>
  );
}
