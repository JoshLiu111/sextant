"use client";

import { useState } from "react";
import { getMessages } from "@/i18n";

/** Two-step delete: nothing is sent until the user confirms. */
export function DeleteAccount() {
  const t = getMessages().account.delete;
  const [confirming, setConfirming] = useState(false);

  return (
    <section className="card mt-10 border-error p-4 md:p-5">
      <h2 className="text-lg">{t.heading}</h2>
      <p className="mt-1 text-sm text-ink-2">{t.body}</p>
      {confirming ? (
        <form method="post" action="/account/delete" className="mt-4 flex flex-wrap items-center gap-3">
          <p role="alert" className="w-full text-sm font-medium text-red-700">
            {t.warning}
          </p>
          <button type="submit" className="btn btn-danger">
            {t.confirm}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setConfirming(false)}
          >
            {t.cancel}
          </button>
        </form>
      ) : (
        <button
          type="button"
          className="btn mt-4 border-error text-error"
          onClick={() => setConfirming(true)}
        >
          {t.button}
        </button>
      )}
    </section>
  );
}
