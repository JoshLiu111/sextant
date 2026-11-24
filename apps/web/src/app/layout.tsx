import type { Metadata, Viewport } from "next";
import { Analytics } from "@vercel/analytics/next";
import { Geist, Hedvig_Letters_Serif } from "next/font/google";
import { AccountMenu } from "@/components/AccountMenu";
import { NavLogo } from "@/components/NavLogo";
import { PageSourcesProvider } from "@/components/PageSources";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteNav } from "@/components/SiteNav";
import { THEME_SCRIPT } from "@/components/ThemeToggle";
import { getMessages } from "@/i18n";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const hedvig = Hedvig_Letters_Serif({
  variable: "--font-hedvig",
  subsets: ["latin"],
  weight: "400",
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
      className={`${geistSans.variable} ${hedvig.variable} h-full antialiased`}
      // data-theme is set by THEME_SCRIPT before hydration.
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col">
        <PageSourcesProvider>
          <SiteNav account={<AccountMenu />} logo={<NavLogo />} />
          {children}
          <SiteFooter />
        </PageSourcesProvider>
        {onVercel && <Analytics />}
      </body>
    </html>
  );
}
