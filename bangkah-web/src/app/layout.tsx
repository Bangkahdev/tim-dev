import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Navbar } from "@/components/navbar";
import { Footer } from "@/components/footer";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

const siteUrl = "https://bangkah.web.id";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Bangkah — Software Studio",
    template: "%s · Bangkah",
  },
  description:
    "Bangkah membangun produk digital, arsitektur sistem, dan tim engineering dengan prosedur jelas, bukti nyata, dan standar kualitas tinggi.",
  keywords: [
    "Bangkah",
    "software studio",
    "software house Indonesia",
    "pengembangan aplikasi",
    "arsitektur sistem",
    "quality assurance",
    "API",
  ],
  authors: [{ name: "Bangkah" }],
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    locale: "id_ID",
    url: siteUrl,
    siteName: "Bangkah",
    title: "Bangkah — Software Studio",
    description:
      "Produk digital, arsitektur sistem, dan tim engineering dengan prosedur jelas serta bukti nyata.",
    images: [{ url: "/assets/bangkah-office-isometric.webp", width: 1200, height: 1200, alt: "Bangkah" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Bangkah — Software Studio",
    description:
      "Produk digital, arsitektur sistem, dan tim engineering dengan prosedur jelas serta bukti nyata.",
    images: ["/assets/bangkah-office-isometric.webp"],
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="id" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <Navbar />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
