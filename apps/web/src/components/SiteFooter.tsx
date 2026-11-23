import { getMessages } from "@/i18n";
import { FooterAttribution } from "./FooterAttribution";

export function SiteFooter() {
  const t = getMessages();
  return (
    <footer className="mt-auto border-t border-black/10 text-sm text-black/70 dark:border-white/15 dark:text-white/70">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6">
        <p className="font-medium">{t.footer.disclaimer}</p>
        <p>{t.footer.analytics}</p>
        <FooterAttribution />
      </div>
    </footer>
  );
}
