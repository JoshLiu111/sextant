import Image from "next/image";
import Link from "next/link";
import { getMessages } from "@/i18n";

export default function NotFound() {
  const t = getMessages();
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col items-start px-4 py-16 md:py-24">
      <div className="art-plate w-full max-w-[20rem]">
        <Image src="/landing/sextant-assets/states/not-found.png" width={640} height={400} alt="" priority sizes="20rem" className="block h-auto w-full" />
      </div>
      <h1 className="mt-10 text-3xl">{t.notFound.heading}</h1>
      <Link href="/" className="btn mt-8">
        {t.notFound.back}
      </Link>
    </main>
  );
}
