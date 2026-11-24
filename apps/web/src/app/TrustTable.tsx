import { getMessages } from "@/i18n";

/**
 * Privacy in the visitor's own questions, one answer per row. The answers state
 * what the code does (see the note on `home.trust` in src/i18n/en.ts).
 */
export function TrustTable() {
  const t = getMessages().home.trust;
  return (
    <section aria-labelledby="trust-heading" className="min-w-0">
      <h2 id="trust-heading" className="border-t border-ink pt-6 text-3xl text-ink">
        {t.heading}
      </h2>
      <p className="mt-4 text-ink-2">{t.intro}</p>
      <dl className="mt-6 border-t border-rule">
        {t.rows.map(([question, answer]) => (
          <div
            key={question}
            className="grid gap-x-8 gap-y-1 border-b border-rule py-4 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:items-baseline"
          >
            <dt className="font-medium text-ink">{question}</dt>
            <dd className="text-ink-2">{answer}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
