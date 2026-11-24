import { getMessages } from "@/i18n";

/**
 * Privacy in the visitor's own questions, one answer per row. The answers state
 * what the code does (see the note on `home.trust` in src/i18n/en.ts).
 */
export function TrustTable() {
  const t = getMessages().home.trust;
  return (
    <section aria-labelledby="trust-heading" className="min-w-0">
      <h2 id="trust-heading" className="border-t border-ink pt-5 text-2xl text-ink">
        {t.heading}
      </h2>
      <p className="mt-2 text-ink-2">{t.intro}</p>
      {/* Two columns of questions, each answer under its question, so the table stays short. */}
      <dl className="mt-4 grid gap-x-8 border-t border-rule md:grid-cols-2">
        {t.rows.map(([question, answer], i) => (
          // An odd last row takes both columns rather than standing alone.
          <div key={question} className={`border-b border-rule py-2.5 ${i === t.rows.length - 1 && t.rows.length % 2 === 1 ? "md:col-span-2" : ""}`}>
            <dt className="font-medium text-ink">{question}</dt>
            <dd className="mt-0.5 text-ink-2">{answer}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
