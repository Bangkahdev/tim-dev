import { useState, type FormEvent } from "react"
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Clock3,
  Mail,
  MapPin,
  ShieldCheck,
} from "lucide-react"
import { SiteHeader } from "@/components/site-header"
import { SiteFooter } from "@/components/site-footer"
import { SectionHeading } from "@/components/section-heading"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Textarea } from "@/components/ui/textarea"
import {
  contact,
  faqs,
  gallery,
  principles,
  processSteps,
  services,
  stats,
  team,
} from "@/data"

function Hero() {
  return (
    <section id="beranda" className="relative border-b border-border">
      <div className="shell grid items-center gap-14 py-16 lg:grid-cols-12 lg:gap-10 lg:py-24">
        <div className="lg:col-span-6">
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-[0.68rem] font-medium tracking-[0.16em] text-muted-foreground uppercase">
            <span className="size-1.5 rounded-full bg-forest" aria-hidden="true" />
            Studio teknologi · Jakarta
          </span>

          <h1 className="editorial mt-7 text-[2.9rem] leading-[0.98] text-ink sm:text-6xl lg:text-[4.35rem]">
            Perangkat lunak yang dibangun dengan cara yang{" "}
            <em className="text-forest italic">lebih manusiawi.</em>
          </h1>

          <p className="mt-7 max-w-xl text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8">
            Bangkah merancang produk, platform, dan sistem kerja yang tenang.
            Tim kecil, keputusan yang tercatat, dan rilis yang bisa
            dipertanggungjawabkan.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Button asChild className="h-11 gap-2 px-5 text-sm">
              <a href="#kapabilitas">
                Lihat kapabilitas
                <ArrowRight aria-hidden="true" />
              </a>
            </Button>
            <Button asChild variant="outline" className="h-11 gap-2 px-5 text-sm">
              <a href="#tim">Kenali tim</a>
            </Button>
          </div>

          <div className="mt-10 flex items-center gap-6 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-2">
              <ShieldCheck className="size-4 text-forest" aria-hidden="true" />
              Persetujuan manusia
            </span>
            <span className="inline-flex items-center gap-2">
              <Clock3 className="size-4 text-forest" aria-hidden="true" />
              Respons 1–2 hari kerja
            </span>
          </div>
        </div>

        <div className="lg:col-span-6">
          <div className="relative mx-auto max-w-2xl">
            <div
              className="absolute -top-4 -left-4 hidden h-full w-full border border-border bg-sage-soft sm:block"
              aria-hidden="true"
            />
            <div className="relative border border-border bg-card p-2">
              <img
                src="/images/office-lobby.png"
                alt="Lobi dan meja resepsionis di markas Bangkah"
                width={1600}
                height={900}
                className="photo aspect-[4/3] w-full object-cover"
              />
            </div>
            <div className="relative -mt-px border border-border bg-paper p-5 sm:absolute sm:-bottom-7 sm:-left-6 sm:mt-0 sm:w-64">
              <p className="eyebrow">Markas aktif</p>
              <p className="mt-2 text-sm leading-6 text-ink">
                7 spesialis, 4 disiplin, satu ruang kerja yang bisa dijelajahi.
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-border bg-card">
        <div className="shell grid grid-cols-2 divide-x divide-border sm:grid-cols-4">
          {stats.map((stat) => (
            <div key={stat.label} className="px-2 py-6 sm:px-6">
              <p className="editorial text-3xl text-forest sm:text-4xl">
                {stat.value}
              </p>
              <p className="mt-1 text-[0.68rem] font-medium tracking-[0.16em] text-muted-foreground uppercase">
                {stat.label}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function DisciplineBand() {
  return (
    <div className="border-b border-forest-deep bg-forest">
      <div className="shell flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-4 text-[0.66rem] font-medium tracking-[0.2em] text-paper/80 uppercase">
        <span>Product engineering</span>
        <span className="hidden text-sage sm:inline">/</span>
        <span>Platform &amp; API</span>
        <span className="hidden text-sage sm:inline">/</span>
        <span>Quality &amp; reliability</span>
        <span className="hidden text-sage sm:inline">/</span>
        <span>AI workflow design</span>
      </div>
    </div>
  )
}

function About() {
  return (
    <section id="tentang" className="border-b border-border">
      <div className="shell grid gap-14 py-20 lg:grid-cols-12 lg:gap-12 lg:py-28">
        <div className="lg:col-span-5">
          <SectionHeading
            eyebrow="Tentang Bangkah"
            title="Kantor bukan latar belakang. Kantor adalah cara kami bekerja."
            description="Bangkah dibangun sebagai satu markas digital: tempat produk, dokumen, rapat, dan keputusan tinggal di ruang yang sama. Kami memakai sistem internal untuk menjaga konteks, bukan untuk menggantikan penilaian manusia."
          />
          <div className="mt-8">
            <a
              href="#kapabilitas"
              className="inline-flex items-center gap-2 text-sm font-medium text-forest underline decoration-border underline-offset-4 transition-colors hover:decoration-forest"
            >
              Cara kami bekerja
              <ArrowUpRight className="size-4" aria-hidden="true" />
            </a>
          </div>
        </div>

        <div className="lg:col-span-7">
          <div className="border border-border bg-card p-2">
            <img
              src="/images/ui-overview.png"
              alt="Ringkasan operasional perusahaan di Command Center Bangkah"
              width={1600}
              height={900}
              className="aspect-[16/10] w-full object-cover"
              loading="lazy"
            />
          </div>

          <div className="mt-8 grid gap-px border border-border bg-border sm:grid-cols-2">
            {principles.map((principle, index) => (
              <div key={principle.title} className="bg-paper p-6">
                <p className="text-[0.66rem] font-medium tracking-[0.18em] text-clay uppercase">
                  0{index + 1}
                </p>
                <h3 className="mt-3 text-base font-semibold text-ink">
                  {principle.title}
                </h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {principle.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function Capabilities() {
  return (
    <section id="kapabilitas" className="border-b border-border bg-paper-deep">
      <div className="shell py-20 lg:py-28">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <SectionHeading
            eyebrow="Kapabilitas"
            title="Empat cara kami membantu produk sampai ke tangan pengguna."
            description="Kami tidak memisahkan strategi, build, dan jaga. Pekerjaan disusun sebagai satu alur dengan bukti di setiap tahap."
          />
          <p className="max-w-xs text-sm leading-6 text-muted-foreground">
            Lingkup bisa dimulai kecil: satu alur, satu rilis, satu tim.
          </p>
        </div>

        <div className="mt-14 space-y-6">
          {services.map((service, index) => (
            <Card
              key={service.id}
              className="gap-0 overflow-hidden rounded-lg border-border bg-card py-0"
            >
              <div className="grid lg:grid-cols-12">
                <div
                  className={
                    "relative border-b border-border lg:col-span-5 lg:border-r lg:border-b-0 " +
                    (index % 2 === 1 ? "lg:order-2 lg:border-r-0 lg:border-l" : "")
                  }
                >
                  <img
                    src={service.image}
                    alt={service.alt}
                    width={1600}
                    height={900}
                    className="photo aspect-[16/10] h-full w-full object-cover lg:aspect-auto lg:min-h-[340px]"
                    loading="lazy"
                  />
                </div>

                <CardContent className="p-7 lg:col-span-7 lg:p-10">
                  <div className="flex items-start justify-between gap-6">
                    <div>
                      <p className="text-[0.66rem] font-medium tracking-[0.2em] text-clay uppercase">
                        {service.number}
                      </p>
                      <h3 className="editorial mt-3 text-3xl text-ink sm:text-4xl">
                        {service.title}
                      </h3>
                    </div>
                    <ArrowUpRight
                      className="mt-1 size-5 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                  </div>

                  <p className="mt-4 max-w-xl text-sm leading-7 text-muted-foreground">
                    {service.summary}
                  </p>

                  <ul className="mt-6 space-y-2.5">
                    {service.points.map((point) => (
                      <li key={point} className="flex gap-3 text-sm text-ink">
                        <Check
                          className="mt-0.5 size-4 shrink-0 text-forest"
                          aria-hidden="true"
                        />
                        {point}
                      </li>
                    ))}
                  </ul>

                  <Separator className="my-6" />

                  <div className="flex flex-wrap gap-2">
                    {service.stack.map((item) => (
                      <Badge
                        key={item}
                        variant="outline"
                        className="rounded-md border-border bg-paper px-2.5 py-1 text-[0.65rem] font-medium tracking-[0.08em] text-muted-foreground uppercase"
                      >
                        {item}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </div>
            </Card>
          ))}
        </div>

        <div className="mt-14 grid gap-px border border-border bg-border md:grid-cols-3">
          {processSteps.map((step) => (
            <div key={step.number} className="bg-paper p-7">
              <p className="text-[0.66rem] font-medium tracking-[0.2em] text-clay uppercase">
                {step.number}
              </p>
              <h3 className="mt-4 text-lg font-semibold text-ink">{step.title}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {step.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Inside() {
  return (
    <section className="border-b border-border">
      <div className="shell py-20 lg:py-28">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <SectionHeading
            eyebrow="Di dalam markas"
            title="Ruang yang dibuat untuk fokus, bukan untuk pamer."
            description="Setiap area punya peran: menerima tamu, mengambil keputusan, membangun, menguji, dan menyimpan jejak pekerjaan."
          />
          <a
            href="#kontak"
            className="inline-flex items-center gap-2 text-sm font-medium text-forest underline decoration-border underline-offset-4 transition-colors hover:decoration-forest"
          >
            Atur kunjungan
            <ArrowUpRight className="size-4" aria-hidden="true" />
          </a>
        </div>

        <div className="mt-12 grid auto-rows-[190px] gap-4 md:grid-cols-3 md:auto-rows-[220px]">
          {gallery.map((item) => (
            <figure
              key={item.src}
              className={`group relative overflow-hidden border border-border bg-card ${item.span ?? ""}`}
            >
              <img
                src={item.src}
                alt={item.alt}
                width={1600}
                height={900}
                className="photo h-full w-full object-cover"
                loading="lazy"
              />
              <figcaption className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-4 border-t border-paper/20 bg-forest px-4 py-3 text-paper">
                <span>
                  <span className="block text-[0.62rem] font-medium tracking-[0.18em] text-sage uppercase">
                    {item.detail}
                  </span>
                  <span className="mt-0.5 block text-sm font-medium">
                    {item.title}
                  </span>
                </span>
                <ArrowUpRight
                  className="size-4 shrink-0 text-sage"
                  aria-hidden="true"
                />
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  )
}

function Team() {
  return (
    <section id="tim" className="border-b border-border bg-paper-deep">
      <div className="shell py-20 lg:py-28">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <SectionHeading
            eyebrow="Tim"
            title="Tujuh spesialis, satu meja keputusan."
            description="Tim inti bekerja dengan peran yang jelas. Setiap orang memiliki area, tapi keputusan penting tetap dibawa ke meja yang sama."
          />
          <div className="border border-border bg-card px-5 py-4">
            <p className="eyebrow">Roster inti</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Management · Engineering · Reception
            </p>
          </div>
        </div>

        <div className="mt-12 grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          {team.map((person) => (
            <article key={person.name} className="bg-card p-6">
              <div className="flex items-center justify-between gap-4">
                <Avatar className="size-12 rounded-md after:rounded-md">
                  <AvatarFallback
                    className={`rounded-md text-sm font-semibold ${person.tone}`}
                  >
                    {person.initials}
                  </AvatarFallback>
                </Avatar>
                <span className="text-[0.6rem] font-medium tracking-[0.16em] text-muted-foreground uppercase">
                  Bangkah
                </span>
              </div>
              <h3 className="mt-5 text-lg font-semibold text-ink">
                {person.name}
              </h3>
              <p className="mt-1 text-xs font-medium tracking-[0.06em] text-forest uppercase">
                {person.role}
              </p>
              <p className="mt-4 text-sm leading-6 text-muted-foreground">
                {person.focus}
              </p>
            </article>
          ))}
        </div>

        <div className="mt-8 flex flex-col gap-4 border border-border bg-card p-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-xl text-sm leading-6 text-muted-foreground">
            Ingin bergabung atau mengajak kolaborasi? Kami membuka percakapan
            untuk peran yang tepat, bukan sekadar menambah kepala.
          </p>
          <Button asChild variant="outline" className="h-10 shrink-0 gap-2 px-4">
            <a href="#kontak">
              Hubungi tim
              <ArrowUpRight aria-hidden="true" />
            </a>
          </Button>
        </div>
      </div>
    </section>
  )
}

function Faq() {
  return (
    <section className="border-b border-border">
      <div className="shell grid gap-12 py-20 lg:grid-cols-12 lg:py-28">
        <div className="lg:col-span-5">
          <SectionHeading
            eyebrow="Pertanyaan"
            title="Hal yang biasanya ditanyakan sebelum mulai."
            description="Kalau ada yang belum terjawab, kirim pesan. Kami menjawab dengan bahasa yang jelas."
          />
        </div>
        <div className="lg:col-span-7">
          <Accordion type="single" collapsible className="w-full">
            {faqs.map((faq, index) => (
              <AccordionItem key={faq.question} value={`item-${index}`}>
                <AccordionTrigger className="text-left text-base font-medium text-ink hover:no-underline">
                  {faq.question}
                </AccordionTrigger>
                <AccordionContent className="text-sm leading-7 text-muted-foreground">
                  {faq.answer}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </div>
    </section>
  )
}

function ContactForm() {
  const [sent, setSent] = useState(false)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const name = String(form.get("name") ?? "")
    const email = String(form.get("email") ?? "")
    const message = String(form.get("message") ?? "")
    const subject = encodeURIComponent(`Percakapan dengan Bangkah — ${name}`)
    const body = encodeURIComponent(
      `Nama: ${name}\nEmail: ${email}\n\n${message}`,
    )
    window.location.href = `mailto:${contact.email}?subject=${subject}&body=${body}`
    setSent(true)
  }

  return (
    <div className="border border-border bg-paper p-6 sm:p-8">
      <p className="eyebrow">Formulir kontak</p>
      <h3 className="editorial mt-3 text-2xl text-ink sm:text-3xl">
        Ceritakan yang sedang Anda bangun.
      </h3>
      <form className="mt-6 space-y-5" onSubmit={handleSubmit}>
        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="name">Nama</Label>
            <Input
              id="name"
              name="name"
              required
              autoComplete="name"
              placeholder="Nama Anda"
              className="h-11 bg-card"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
              placeholder="nama@perusahaan.com"
              className="h-11 bg-card"
            />
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="message">Pesan</Label>
          <Textarea
            id="message"
            name="message"
            required
            rows={5}
            placeholder="Konteks singkat, tujuan, dan tenggat yang Anda bayangkan."
            className="resize-none bg-card"
          />
        </div>
        <Button type="submit" className="h-11 w-full gap-2 px-5 sm:w-auto">
          Kirim pesan
          <ArrowUpRight aria-hidden="true" />
        </Button>
        <p className="text-xs leading-5 text-muted-foreground">
          {sent
            ? "Aplikasi email Anda sedang dibuka. Jika tidak terbuka, kirim langsung ke " + contact.email + "."
            : "Formulir ini membuka aplikasi email Anda. Tidak ada data yang dikirim ke server."}
        </p>
      </form>
    </div>
  )
}

function Contact() {
  return (
    <section id="kontak" className="bg-forest-deep">
      <div className="shell grid gap-12 py-20 lg:grid-cols-12 lg:py-28">
        <div className="lg:col-span-6">
          <SectionHeading
            tone="dark"
            eyebrow="Kontak"
            title="Mulai dari percakapan yang sederhana."
            description="Ceritakan masalah, bukan hanya solusi. Kami akan membantu memetakan langkah pertama yang masuk akal."
          />

          <div className="mt-10 space-y-5 text-sm text-paper/80">
            <a
              href={`mailto:${contact.email}`}
              className="flex items-center gap-3 transition-colors hover:text-paper"
            >
              <span className="flex size-9 items-center justify-center border border-paper/20 text-sage">
                <Mail className="size-4" aria-hidden="true" />
              </span>
              {contact.email}
            </a>
            <p className="flex items-center gap-3">
              <span className="flex size-9 items-center justify-center border border-paper/20 text-sage">
                <MapPin className="size-4" aria-hidden="true" />
              </span>
              {contact.location}
            </p>
            <p className="flex items-center gap-3">
              <span className="flex size-9 items-center justify-center border border-paper/20 text-sage">
                <Clock3 className="size-4" aria-hidden="true" />
              </span>
              {contact.hours}
            </p>
          </div>

          <p className="mt-8 max-w-md border-l-2 border-sage pl-4 text-sm leading-6 text-paper/60">
            {contact.response}
          </p>
        </div>

        <div className="lg:col-span-6">
          <ContactForm />
        </div>
      </div>
    </section>
  )
}

function App() {
  return (
    <div className="min-h-screen bg-paper">
      <SiteHeader />
      <main>
        <Hero />
        <DisciplineBand />
        <About />
        <Capabilities />
        <Inside />
        <Team />
        <Faq />
        <Contact />
      </main>
      <SiteFooter />
    </div>
  )
}

export default App
