import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mundial Predictor 2026 | Modelo + Agentes en vivo",
  description:
    "Resultados, probabilidades, eliminatorias y debate multiagente del Mundial 2026, evaluados contra la realidad.",
  openGraph: {
    title: "Mundial Predictor 2026",
    description: "Modelo estadístico, agentes de IA y resultados reales en un mismo sistema vivo.",
    type: "website",
    url: "https://mundial-predictor.vercel.app",
    images: [
      {
        url: "https://mundial-predictor.vercel.app/api/og",
        width: 1200,
        height: 630,
        alt: "Mundial Predictor 2026 - modelo, agentes y resultados en vivo",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Mundial Predictor 2026",
    description: "Modelo estadístico, agentes de IA y resultados reales en un mismo sistema vivo.",
    images: ["https://mundial-predictor.vercel.app/api/og"],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Barlow+Condensed:wght@400;600;700;800&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased">
        {children}
        <Analytics />
      </body>
    </html>
  );
}
