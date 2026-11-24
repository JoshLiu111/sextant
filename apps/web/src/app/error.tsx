"use client";

import Image from "next/image";
import Link from "next/link";
import { getMessages } from "@/i18n";

/** The page-level error boundary: a render that threw. Failed requests show an ErrorNotice in place instead. */
export default function PageError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = getMessages().pageError;
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col items-start px-4 py-16 md:py-24">
      <div className="art-plate w-full max-w-[20rem]">
        <Image src="/landing/sextant-assets/states/error.png" width={640} height={400} alt="" sizes="20rem" className="block h-auto w-full" />
      </div>
      <h1 className="mt-10 text-3xl">{t.heading}</h1>
      <p className="mt-4 text-ink-2">{t.body}</p>
      <div className="mt-8 flex flex-wrap gap-3">
        <button type="button" onClick={reset} className="btn btn-primary">
          {t.retry}
        </button>
        <Link href="/" className="btn">
          {t.back}
        </Link>
      </div>
    </main>
  );
}
