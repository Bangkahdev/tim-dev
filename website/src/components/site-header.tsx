import { useEffect, useState } from "react"
import { ArrowUpRight, Menu } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { navItems } from "@/data"
import { cn } from "@/lib/utils"

function useActiveSection() {
  const [active, setActive] = useState("beranda")

  useEffect(() => {
    const sections = navItems
      .map((item) => document.querySelector(item.href))
      .filter((node): node is Element => Boolean(node))

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (visible?.target.id) setActive(visible.target.id)
      },
      { rootMargin: "-22% 0px -62% 0px", threshold: [0.05, 0.25, 0.5] },
    )

    sections.forEach((section) => observer.observe(section))
    return () => observer.disconnect()
  }, [])

  return active
}

function Wordmark() {
  return (
    <a href="#beranda" className="group flex items-center gap-3">
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
  )
}

export function SiteHeader() {
  const active = useActiveSection()

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-paper">
      <div className="shell flex h-20 items-center justify-between gap-6">
        <Wordmark />

        <nav className="hidden items-center gap-1 lg:flex" aria-label="Navigasi utama">
          {navItems.map((item) => {
            const isActive = active === item.href.slice(1)
            return (
              <a
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-md px-3 py-2 text-[0.82rem] font-medium text-muted-foreground transition-colors hover:bg-paper-deep hover:text-ink",
                  isActive && "bg-paper-deep text-ink",
                )}
              >
                {item.label}
              </a>
            )
          })}
        </nav>

        <div className="flex items-center gap-3">
          <Button asChild className="hidden h-10 gap-2 px-4 sm:inline-flex">
            <a href="#kontak">
              Mulai percakapan
              <ArrowUpRight aria-hidden="true" />
            </a>
          </Button>

          <Sheet>
            <SheetTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                className="size-10 lg:hidden"
                aria-label="Buka menu"
              >
                <Menu aria-hidden="true" />
              </Button>
            </SheetTrigger>
            <SheetContent className="w-[88vw] bg-paper sm:max-w-sm">
              <SheetHeader>
                <SheetTitle className="text-left">
                  <Wordmark />
                </SheetTitle>
                <SheetDescription className="text-left">
                  Navigasi markas Bangkah.
                </SheetDescription>
              </SheetHeader>
              <nav className="mt-8 flex flex-col" aria-label="Navigasi seluler">
                {navItems.map((item) => (
                  <SheetClose key={item.href} asChild>
                    <a
                      href={item.href}
                      className="flex items-center justify-between border-b border-border py-4 text-lg text-ink"
                    >
                      {item.label}
                      <ArrowUpRight
                        className="size-4 text-muted-foreground"
                        aria-hidden="true"
                      />
                    </a>
                  </SheetClose>
                ))}
              </nav>
              <div className="mt-8 rounded-md border border-border bg-card p-4">
                <p className="eyebrow">Markas</p>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Jakarta, Indonesia
                  <br />
                  Senin–Jumat, 09.00–17.00 WIB
                </p>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  )
}
