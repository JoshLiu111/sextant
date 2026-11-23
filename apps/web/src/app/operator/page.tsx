import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { getMessages } from "@/i18n";
import { sessionToken } from "@/lib/auth/session";
import { fetchAiUsage, type DayUsage, type UsageTotals, type UserUsage } from "@/lib/operator";

// Operator view of AI usage (story 95). src/proxy.ts already turned non-operators
// away with a 404 before rendering; the compute service checks again here.

const t = getMessages();
const c = t.operator.columns;

export const metadata: Metadata = { title: t.operator.heading, robots: { index: false, follow: false } };

const WHOLE = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});
const PRICE = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 });

const th = "px-3 py-2 text-left font-medium";
const thNum = "px-3 py-2 text-right font-medium";
const td = "px-3 py-2";
const tdNum = "px-3 py-2 text-right tabular-nums";

function TotalCells({ row }: { row: UsageTotals }) {
  return (
    <>
      <td className={tdNum}>{WHOLE.format(row.calls)}</td>
      <td className={tdNum}>{WHOLE.format(row.failed_calls)}</td>
      <td className={tdNum}>{WHOLE.format(row.input_tokens)}</td>
      <td className={tdNum}>{WHOLE.format(row.output_tokens)}</td>
      <td className={tdNum}>{USD.format(row.estimated_cost_usd)}</td>
    </>
  );
}

function TotalHeaders() {
  return (
    <>
      <th scope="col" className={thNum}>{c.calls}</th>
      <th scope="col" className={thNum}>{c.failedCalls}</th>
      <th scope="col" className={thNum}>{c.inputTokens}</th>
      <th scope="col" className={thNum}>{c.outputTokens}</th>
      <th scope="col" className={thNum}>{c.cost}</th>
    </>
  );
}

function UserCell({ row }: { row: UserUsage }) {
  return (
    <td className={td}>
      {row.email}
      {row.name && <span className="text-black/60 dark:text-white/60"> ({row.name})</span>}
    </td>
  );
}

const tableClass = "mt-3 w-full border-collapse text-sm [&_tbody_tr]:border-t [&_tbody_tr]:border-black/10 dark:[&_tbody_tr]:border-white/10";

function PerUserTable({ users, totals }: { users: UserUsage[]; totals: UsageTotals }) {
  return (
    <table className={tableClass} aria-label={t.operator.perUser}>
      <caption className="text-left text-lg font-semibold">{t.operator.perUser}</caption>
      <thead>
        <tr>
          <th scope="col" className={th}>{c.user}</th>
          <TotalHeaders />
        </tr>
      </thead>
      <tbody>
        {users.map((u) => (
          <tr key={u.user_id}>
            <UserCell row={u} />
            <TotalCells row={u} />
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr className="border-t-2 border-black/20 font-semibold dark:border-white/20" data-testid="ai-usage-totals">
          <th scope="row" className={th}>{t.operator.totals}</th>
          <TotalCells row={totals} />
        </tr>
      </tfoot>
    </table>
  );
}

function PerDayTable({ days }: { days: DayUsage[] }) {
  return (
    <table className={tableClass} aria-label={t.operator.perDay}>
      <caption className="text-left text-lg font-semibold">{t.operator.perDay}</caption>
      <thead>
        <tr>
          <th scope="col" className={th}>{c.day}</th>
          <th scope="col" className={th}>{c.user}</th>
          <TotalHeaders />
        </tr>
      </thead>
      <tbody>
        {days.map((d) => (
          <tr key={`${d.day}-${d.user_id}`}>
            <td className={`${td} tabular-nums`}>{d.day}</td>
            <UserCell row={d} />
            <TotalCells row={d} />
          </tr>
        ))}
      </tbody>
    </table>
  );
}

async function AiUsage() {
  const result = await fetchAiUsage(await sessionToken());
  if (result.kind === "not_found") notFound();
  if (result.kind === "failed") {
    return (
      <div className="mt-6">
        <ErrorNotice title={t.operator.errorHeading} message={t.operator.unavailable} />
      </div>
    );
  }
  const { report } = result;
  return (
    <>
      <p className="mt-2 text-black/70 dark:text-white/70">{t.operator.intro(report.since, report.until)}</p>
      <p className="mt-1 text-sm text-black/60 dark:text-white/60" data-testid="ai-usage-pricing">
        {t.operator.pricing(
          PRICE.format(report.pricing.input_usd_per_mtok),
          PRICE.format(report.pricing.output_usd_per_mtok),
        )}
      </p>
      <p className="mt-1 text-sm text-black/60 dark:text-white/60">{t.operator.failedNote}</p>
      {report.users.length === 0 ? (
        <p className="mt-6" data-testid="ai-usage-empty">{t.operator.empty}</p>
      ) : (
        <div className="mt-6 space-y-10 overflow-x-auto">
          <PerUserTable users={report.users} totals={report.totals} />
          <PerDayTable days={report.days} />
        </div>
      )}
    </>
  );
}

export default function OperatorPage() {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{t.operator.heading}</h1>
      <Suspense fallback={null}>
        <AiUsage />
      </Suspense>
    </main>
  );
}
