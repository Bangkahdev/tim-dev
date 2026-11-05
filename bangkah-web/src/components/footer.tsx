"use client";

import Link from "next/link";
import { useState, useEffect } from "react";

const footerLinks = [
  { href: "#tentang", label: "Tentang" },
  { href: "#layanan", label: "Layanan" },
  { href: "#tim", label: "Tim" },
  { href: "#proyek", label: "Proyek" },
  { href: "#kontak", label: "Kontak" },
];

const internalLinks = [
  { href: "https://mail.bangkah.web.id", label: "Mail perusahaan" },
  { href: "https://files.bangkah.web.id", label: "Portal file" },
  { href: "https://bangkah.web.id/api/health", label: "Status layanan" },
];

export function Footer() {
  const [year, setYear] = useState<number>(2026);

  useEffect(() => {
    setYear(new Date().getFullYear());
  }, []);

  return (
    <footer className="border-t border-border bg-muted/40">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-4">
          <div className="md:col-span-2">
            <Link href="/" className="mb-4 flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-lg font-bold text-primary-foreground">
                B
              </div>
              <span className="flex flex-col leading-none">
                <span className="text-lg font-semibold tracking-tight">Bangkah</span>
                <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  Software Studio
                </span>
              </span>
            </Link>
            <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">
              Perusahaan software yang beroperasi dengan prosedur jelas, akuntabilitas penuh, dan
              standar kualitas tinggi dalam setiap rilis.
            </p>
            <p className="mt-4 text-sm text-muted-foreground">
              <a href="mailto:owner@bangkah.web.id" className="text-primary hover:underline">
                owner@bangkah.web.id
              </a>
              <span className="mx-2 text-border">·</span>
              Indonesia
            </p>
          </div>

          <div>
            <h3 className="mb-4 text-sm font-semibold">Navigasi</h3>
            <ul className="space-y-2">
              {footerLinks.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="mb-4 text-sm font-semibold">Layanan Internal</h3>
            <ul className="space-y-2">
              {internalLinks.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
              Akses internal memerlukan kredensial perusahaan.
            </p>
          </div>
        </div>

        <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-border pt-8 sm:flex-row">
          <p className="text-xs text-muted-foreground">
            &copy; {year} Bangkah. Hak cipta dilindungi.
          </p>
          <p className="text-xs text-muted-foreground">
            Dibangun dengan presisi dan keandalan.
          </p>
        </div>
      </div>
    </footer>
  );
}
