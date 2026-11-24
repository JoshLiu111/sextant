import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { getMessages } from "@/i18n";
import { sessionToken } from "@/lib/auth/session";
import {
  fetchAiUsage,
  fetchUsers,
  WINDOW_DAYS,
  windowDays,
  type DayUsage,
  type UsageTotals,
  type UserUsage,
  type WindowDays,
} from "@/lib/operator";

// Operator view: users (issue #51) and AI usage (story 95). src/proxy.ts already turned non-operators
// away with a 404 before rendering; the compute service checks again here. `?days=` picks the
// window (WINDOW_DAYS) the sign-ups and AI usage cover.

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

const th = "px-3 py-2 text-left text-xs font-medium text-muted first:pl-0";
const thNum = "px-3 py-2 text-right text-xs font-medium text-muted last:pr-0";
const td = "px-3 py-2 first:pl-0";
const tdNum = "px-3 py-2 text-right tabular-nums last:pr-0";

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
      {row.name && <span className="text-muted"> ({row.name})</span>}
    </td>
  );
}

const tableClass = "mt-3 w-full border-collapse text-sm [&_thead_tr]:border-b [&_thead_tr]:border-ink [&_tbody_tr]:border-t [&_tbody_tr]:border-rule [&_tbody_tr:first-child]:border-t-0";

function PerUserTable({ users, totals }: { users: UserUsage[]; totals: UsageTotals }) {
  return (
    <table className={tableClass} aria-label={t.operator.perUser}>
      <caption className="pb-2 text-left font-display text-lg">{t.operator.perUser}</caption>
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
        <tr className="border-t border-ink font-medium" data-testid="ai-usage-totals">
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
      <caption className="pb-2 text-left font-display text-lg">{t.operator.perDay}</caption>
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

async function AiUsage({ days }: { days: WindowDays }) {
  const result = await fetchAiUsage(await sessionToken(), days);
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
      <p className="mt-3 max-w-[65ch] text-ink-2">{t.operator.intro(report.since, report.until)}</p>
      <p className="mt-1 max-w-[75ch] text-sm tabular-nums text-muted" data-testid="ai-usage-pricing">
        {t.operator.pricing(
          PRICE.format(report.pricing.input_usd_per_mtok),
          PRICE.format(report.pricing.output_usd_per_mtok),
        )}
      </p>
      <p className="mt-1 max-w-[75ch] text-sm text-muted">{t.operator.failedNote}</p>
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

const u = t.operator.users;

function Stat({ label, value, testId }: { label: string; value: number; testId: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="figure-display mt-2 text-3xl" data-testid={testId}>
        {WHOLE.format(value)}
      </dd>
    </div>
  );
}

async function Users({ days }: { days: WindowDays }) {
  const result = await fetchUsers(await sessionToken(), days);
  if (result.kind === "not_found") notFound();
  if (result.kind === "failed") {
    return (
      <div className="mt-3">
        <ErrorNotice title={u.errorHeading} message={u.unavailable} />
      </div>
    );
  }
  const { report } = result;
  return (
    <>
      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-5 border-t border-ink pt-4 sm:grid-cols-3">
        <Stat label={u.total} value={report.total_users} testId="users-total" />
        {report.signed_in_within.map((s) => (
          <Stat
            key={s.days}
            label={u.signedInWithin(s.days)}
            value={s.users}
            testId={`users-signed-in-${s.days}`}
          />
        ))}
      </dl>
      <p className="mt-3 max-w-[75ch] text-sm text-muted">{u.signedInNote}</p>
      <div className="mt-6 overflow-x-auto">
        <table className={tableClass} aria-label={u.signUps}>
          <caption className="pb-2 text-left font-display text-lg">{u.signUps}</caption>
          <thead>
            <tr>
              <th scope="col" className={th}>{u.columns.day}</th>
              <th scope="col" className={thNum}>{u.columns.signUps}</th>
            </tr>
          </thead>
          <tbody>
            {report.sign_ups.map((d) => (
              <tr key={d.day}>
                <td className={`${td} tabular-nums`}>{d.day}</td>
                <td className={tdNum}>{WHOLE.format(d.users)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-sm tabular-nums text-muted">{u.signUpsIntro(report.since, report.until)}</p>
      </div>
    </>
  );
}

function WindowPicker({ days }: { days: WindowDays }) {
  return (
    <nav aria-label={t.operator.window.label} className="mt-5 flex flex-wrap gap-2 text-sm">
      {WINDOW_DAYS.map((d) => (
        <Link
          key={d}
          href={`/operator?days=${d}`}
          aria-current={d === days ? "page" : undefined}
          className="btn btn-sm tabular-nums aria-[current=page]:bg-paper-2 aria-[current=page]:shadow-[inset_0_-2px_0_var(--color-accent)]"
        >
          {t.operator.window.option(d)}
        </Link>
      ))}
    </nav>
  );
}

async function Report({ searchParams }: { searchParams: PageProps<"/operator">["searchParams"] }) {
  const days = windowDays((await searchParams).days);
  return (
    <>
      <WindowPicker days={days} />
      <section aria-labelledby="operator-users" className="mt-10">
        <h2 id="operator-users" className="text-2xl">{u.heading}</h2>
        <Suspense fallback={null}>
          <Users days={days} />
        </Suspense>
      </section>
      <section aria-labelledby="operator-ai-usage" className="mt-12 border-t border-rule pt-10">
        <h2 id="operator-ai-usage" className="text-2xl">{t.operator.aiUsageHeading}</h2>
        <Suspense fallback={null}>
          <AiUsage days={days} />
        </Suspense>
      </section>
    </>
  );
}

export default function OperatorPage({ searchParams }: PageProps<"/operator">) {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 pb-16 pt-10 md:px-6">
      <h1 className="text-3xl">{t.operator.heading}</h1>
      <Suspense fallback={null}>
        <Report searchParams={searchParams} />
      </Suspense>
    </main>
  );
}
