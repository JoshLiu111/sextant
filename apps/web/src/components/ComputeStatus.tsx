import { Suspense } from "react";
import { getMessages } from "@/i18n";
import { getComputeHealth } from "@/lib/compute";

async function ComputeStatusValue() {
  const t = getMessages();
  const health = await getComputeHealth();
  const online = health !== null;
  return (
    <p data-testid="compute-status" className="text-sm">
      <span
        aria-hidden
        className={`mr-2 inline-block h-2 w-2 rounded-full ${online ? "bg-success" : "bg-error"}`}
      />
      {t.compute.label}: {online ? `${t.compute.online} (v${health.version})` : t.compute.offline}
    </p>
  );
}

/** Live health of the Python compute service, fetched on every request. */
export function ComputeStatus() {
  const t = getMessages();
  return (
    <Suspense
      fallback={
        <p className="text-sm">
          {t.compute.label}: {t.compute.checking}
        </p>
      }
    >
      <ComputeStatusValue />
    </Suspense>
  );
}
