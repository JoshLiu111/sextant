import { getMessages } from "@/i18n";
import { FooterAttribution } from "./FooterAttribution";

/** The colophon: the disclaimer set as the statement, then analytics and the page's data sources. */
export function SiteFooter() {
  const t = getMessages();
  return (
    <footer className="proof mt-auto border-t border-ink">
      <div className="mx-auto grid max-w-7xl gap-x-8 gap-y-6 px-4 pb-12 pt-10 text-sm text-ink-2 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:px-6">
        <div className="space-y-3">
          <p className="font-display text-2xl leading-tight text-ink">{t.site.name}</p>
          <p className="max-w-[48ch] font-medium text-ink">{t.footer.disclaimer}</p>
        </div>
        <div className="space-y-3 md:border-l md:border-rule md:pl-8">
          <p className="max-w-[60ch]">{t.footer.analytics}</p>
          <FooterAttribution />
        </div>
      </div>
    </footer>
  );
}
