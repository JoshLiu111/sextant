import type { Metadata, Viewport } from "next";
import { Analytics } from "@vercel/analytics/next";
import { Geist, Geist_Mono } from "next/font/google";
import { AccountMenu } from "@/components/AccountMenu";
import { PageSourcesProvider } from "@/components/PageSources";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteNav } from "@/components/SiteNav";
import { getMessages } from "@/i18n";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const t = getMessages();

// Vercel Web Analytics only on Vercel deployments: elsewhere (local dev, e2e, CI)
// the component would still fetch Vercel's script, so it isn't rendered at all.
const onVercel = process.env.VERCEL === "1";

export const metadata: Metadata = {
  title: { default: t.site.name, template: `%s | ${t.site.name}` },
  description: t.site.tagline,
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <PageSourcesProvider>
          <SiteNav account={<AccountMenu />} />
          {children}
          <SiteFooter />
        </PageSourcesProvider>
        {onVercel && <Analytics />}
      </body>
    </html>
  );
}
