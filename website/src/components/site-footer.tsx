import { ArrowUpRight, Mail, MapPin } from "lucide-react"
import { Separator } from "@/components/ui/separator"
import { contact, navItems } from "@/data"

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-paper-deep">
      <div className="shell py-14">
        <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr]">
          <div>
            <a href="#beranda" className="flex items-center gap-3">
              <span className="editorial flex size-10 items-center justify-center rounded-md bg-forest text-[1.55rem] leading-none text-paper">
                B
              </span>
              <span className="flex flex-col leading-none">
                <span className="text-[0.95rem] font-semibold tracking-[0.16em] text-ink">
                  BANGKAH
                </span>
                <span className="mt-1 text-[0.58rem] font-medium tracking-[0.18em] text-muted-foreground">
                  COMPANY / TECHNOLOGY
                </span>
              </span>
            </a>
            <p className="mt-6 max-w-sm text-sm leading-7 text-muted-foreground">
              Studio teknologi yang membangun produk, platform, dan cara kerja
              yang lebih tenang, terukur, dan bisa dipertanggungjawabkan.
            </p>
          </div>

          <div>
            <p className="eyebrow">Navigasi</p>
            <ul className="mt-4 space-y-3">
              {navItems.map((item) => (
                <li key={item.href}>
                  <a
                    href={item.href}
                    className="text-sm text-muted-foreground transition-colors hover:text-ink"
                  >
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <p className="eyebrow">Kontak</p>
            <ul className="mt-4 space-y-3 text-sm text-muted-foreground">
              <li>
                <a
                  href={`mailto:${contact.email}`}
                  className="inline-flex items-center gap-2 transition-colors hover:text-ink"
                >
                  <Mail className="size-4" aria-hidden="true" />
                  {contact.email}
                </a>
              </li>
              <li className="inline-flex items-center gap-2">
                <MapPin className="size-4" aria-hidden="true" />
                {contact.location}
              </li>
              <li>
                <a
                  href="#kontak"
                  className="inline-flex items-center gap-2 transition-colors hover:text-ink"
                >
                  Mulai percakapan
                  <ArrowUpRight className="size-4" aria-hidden="true" />
                </a>
              </li>
            </ul>
          </div>
        </div>

        <Separator className="my-10" />

        <div className="flex flex-col gap-3 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 Bangkah. Seluruh hak cipta dilindungi.</p>
          <p className="tracking-[0.14em] uppercase">
            Bangkah.web.id · Jakarta
          </p>
        </div>
      </div>
    </footer>
  )
}
