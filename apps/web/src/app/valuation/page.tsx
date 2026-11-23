import type { Metadata } from "next";
import { ComingSoon } from "@/components/ComingSoon";
import { getMessages } from "@/i18n";

export const metadata: Metadata = { title: getMessages().tools["valuation"].name };

export default function Page() {
  return <ComingSoon slug="valuation" />;
}
