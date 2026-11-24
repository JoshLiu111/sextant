import Link from "next/link";
import { getMessages } from "@/i18n";

export default function NotFound() {
  const t = getMessages();
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-3xl">{t.notFound.heading}</h1>
      <Link href="/" className="mt-6 inline-block underline">
        {t.notFound.back}
      </Link>
    </main>
  );
}
