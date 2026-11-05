"use client";

import Image from "next/image";
import { useState } from "react";
import {
  ArrowRight,
  BadgeCheck,
  Braces,
  Building2,
  CheckCircle2,
  Code2,
  Gauge,
  Layers3,
  Mail,
  MapPin,
  Network,
  Rocket,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

const services = [
  {
    icon: Code2,
    title: "Pengembangan Produk",
    description:
      "Aplikasi web, mobile, dan desktop yang dirancang untuk dipakai sehari-hari — bukan sekadar demo.",
  },
  {
    icon: Layers3,
    title: "Arsitektur Sistem",
    description:
      "Perancangan infrastruktur, integrasi, dan batas layanan yang skalabel serta mudah dirawat.",
  },
  {
    icon: ShieldCheck,
    title: "Quality Assurance",
    description:
      "Pengujian manual dan otomatis, evidence rilis, serta audit trail untuk setiap perubahan penting.",
  },
  {
    icon: Network,
    title: "API & Infrastruktur",
    description:
      "API berperforma tinggi, deployment otomatis, observabilitas, dan pengelolaan layanan cloud.",
  },
];

const team = [
  {
    id: "owner",
    name: "Owner",
    role: "Founder & CEO",
    email: "owner@bangkah.web.id",
    image: "/assets/owner.webp",
    division: "Executive",
    note: "Arah perusahaan dan keputusan akhir.",
  },
  {
    id: "lead",
    name: "Arman",
    role: "Lead Manager",
    email: "arman@bangkah.web.id",
    image: "/assets/lead.webp",
    division: "Executive",
    note: "Koordinasi tim dan eksekusi prioritas.",
  },
  {
    id: "coo",
    name: "Sinta",
    role: "COO / Project Manager",
    email: "sinta@bangkah.web.id",
    image: "/assets/coo.webp",
    division: "Operations",
    note: "Perencanaan proyek dan ritme operasional.",
  },
  {
    id: "architect",
    name: "Raka",
    role: "System Architect",
    email: "raka@bangkah.web.id",
    image: "/assets/architect.webp",
    division: "Engineering",
    note: "Arsitektur, keputusan teknis, dan standar.",
  },
  {
    id: "backend",
    name: "Bima",
    role: "Backend Developer",
    email: "bima@bangkah.web.id",
    image: "/assets/backend.webp",
    division: "Engineering",
    note: "Layanan, data, dan integrasi sistem.",
  },
  {
    id: "api",
    name: "Naya",
    role: "API Specialist",
    email: "naya@bangkah.web.id",
    image: "/assets/api.webp",
    division: "Engineering",
    note: "Kontrak API dan performa layanan.",
  },
  {
    id: "frontend",
    name: "Dira",
    role: "Frontend Developer",
    email: "dira@bangkah.web.id",
    image: "/assets/frontend.webp",
    division: "Engineering",
    note: "Antarmuka, aksesibilitas, dan pengalaman pengguna.",
  },
  {
    id: "qa",
    name: "Tika",
    role: "QA Engineer",
    email: "tika@bangkah.web.id",
    image: "/assets/qa.webp",
    division: "Quality",
    note: "Verifikasi rilis dan bukti kualitas.",
  },
  {
    id: "reception",
    name: "Mira",
    role: "Receptionist",
    email: "mira@bangkah.web.id",
    image: "",
    division: "Front Office",
    note: "Titik kontak pertama dan layanan tamu.",
  },
];

const projects = [
  {
    title: "Bangkah Company Simulator",
    description:
      "Kantor perusahaan yang dapat dijelajahi, terhubung langsung ke data operasional nyata: tugas, rapat, dokumen, dan approval.",
    tag: "Desktop + Backend",
    status: "Live",
  },
  {
    title: "Bangkah AI Office",
    description:
      "Platform koordinasi tim yang menghubungkan perencanaan, eksekusi, dan pelaporan dalam satu alur kerja yang dapat diaudit.",
    tag: "Web Platform",
    status: "Live",
  },
  {
    title: "Office Automation Suite",
    description:
      "Otomatisasi administrasi perusahaan: manajemen tugas, notulen, arsip digital, dan alur persetujuan yang aman.",
    tag: "Automation",
    status: "In development",
  },
];

const process = [
  {
    step: "01",
    title: "Discovery",
    description: "Memahami masalah, batasan, dan definisi sukses bersama pemilik produk.",
  },
  {
    step: "02",
    title: "Design & Arsitektur",
    description: "Merancang alur, kontrak API, dan keputusan teknis sebelum satu baris kode ditulis.",
  },
  {
    step: "03",
    title: "Build",
    description: "Implementasi inkremental dengan review, dokumentasi, dan lingkungan uji yang konsisten.",
  },
  {
    step: "04",
    title: "Verify",
    description: "QA, pengujian regresi, dan bukti rilis. Tidak ada klaim selesai tanpa bukti.",
  },
  {
    step: "05",
    title: "Release & Operate",
    description: "Peluncuran terukur, pemantauan, dan siklus perbaikan berkelanjutan.",
  },
];

const principles = [
  {
    icon: BadgeCheck,
    title: "Akuntabilitas",
    description:
      "Setiap pekerjaan punya pemilik, status, dan bukti penyelesaian. Keputusan tercatat dan dapat ditinjau kembali.",
  },
  {
    icon: Gauge,
    title: "Kualitas",
    description:
      "Kualitas bukan klaim di akhir proyek. Ia dibangun lewat review, pengujian, dan standar yang konsisten sejak awal.",
  },
  {
    icon: Workflow,
    title: "Transparansi",
    description:
      "Owner dan tim melihat hal yang sama: prioritas, hambatan, risiko, dan hasil — tanpa laporan yang dipercantik.",
  },
];

export default function Home() {
  const [status, setStatus] = useState<"idle" | "sending" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);

    setStatus("sending");
    setErrorMessage("");

    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: data.get("name"),
          email: data.get("email"),
          company: data.get("company"),
          message: data.get("message"),
          website: data.get("website"),
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(payload?.error || "Pesan belum dapat dikirim.");
      }

      form.reset();
      setStatus("success");
    } catch (error) {
      setStatus("error");
      setErrorMessage(error instanceof Error ? error.message : "Terjadi kesalahan.");
    }
  }

  return (
    <div className="flex flex-col">
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-border">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(70,192,138,0.12),transparent_45%),radial-gradient(circle_at_85%_10%,rgba(240,181,86,0.08),transparent_40%)]" />
        <div className="relative mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
          <div className="grid grid-cols-1 items-center gap-14 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="flex flex-col gap-7">
              <Badge variant="secondary" className="w-fit gap-1.5 px-3 py-1">
                <Sparkles className="h-3.5 w-3.5 text-primary" />
                Software studio · Indonesia
              </Badge>
              <h1 className="max-w-2xl text-4xl font-bold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">
                Software yang dibangun dengan standar{" "}
                <span className="text-primary">perusahaan nyata.</span>
              </h1>
              <p className="max-w-xl text-lg leading-relaxed text-muted-foreground">
                Bangkah membangun produk digital, arsitektur sistem, dan tim engineering yang bekerja
                dengan prosedur jelas, bukti nyata, dan rasa tanggung jawab atas hasil.
              </p>
              <div className="flex flex-col gap-3 pt-1 sm:flex-row">
                <a
                  href="#kontak"
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
                >
                  Mulai percakapan
                  <ArrowRight className="h-4 w-4" />
                </a>
                <a
                  href="#tim"
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-background px-6 py-3 text-sm font-medium transition-colors hover:bg-muted"
                >
                  Kenali tim kami
                </a>
              </div>
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pt-2 text-sm text-muted-foreground">
                <span className="inline-flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-primary" /> 7 spesialis inti
                </span>
                <span className="inline-flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-primary" /> Proses berbasis bukti
                </span>
                <span className="inline-flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-primary" /> Audit trail
                </span>
              </div>
            </div>

            <div className="relative">
              <div className="overflow-hidden rounded-2xl border border-border bg-card p-3 shadow-2xl shadow-black/30">
                <Image
                  src="/assets/bangkah-office-isometric.webp"
                  alt="Ilustrasi kantor Bangkah"
                  width={960}
                  height={960}
                  className="h-auto w-full rounded-xl object-cover"
                  priority
                />
              </div>
              <div className="absolute -bottom-6 left-6 right-6 rounded-xl border border-border bg-background/95 p-4 shadow-xl backdrop-blur sm:left-10 sm:right-10">
                <div className="grid grid-cols-3 divide-x divide-border text-center">
                  <div className="px-2">
                    <p className="text-xl font-bold text-primary">08</p>
                    <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Orang inti</p>
                  </div>
                  <div className="px-2">
                    <p className="text-xl font-bold text-primary">04</p>
                    <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Layanan</p>
                  </div>
                  <div className="px-2">
                    <p className="text-xl font-bold text-primary">100%</p>
                    <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Berbasis bukti</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Tentang */}
      <section id="tentang" className="border-b border-border">
        <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-12 lg:grid-cols-[0.9fr_1.1fr]">
            <div>
              <Badge variant="secondary" className="mb-4">
                Tentang Kami
              </Badge>
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
                Perusahaan kecil dengan standar operasi yang serius.
              </h2>
              <div className="mt-6 space-y-4 text-muted-foreground">
                <p className="leading-relaxed">
                  Bangkah didirikan dengan prinsip bahwa perusahaan software harus berjalan seperti
                  perusahaan nyata: ada prosedur, akuntabilitas, dan standar kualitas yang jelas.
                </p>
                <p className="leading-relaxed">
                  Kami tidak hanya menulis kode. Kami membangun sistem yang bisa diandalkan, dipelihara,
                  dan berkembang — bersama tim yang tahu persis apa yang sedang dikerjakan dan mengapa.
                </p>
              </div>
              <div className="mt-8 rounded-xl border border-border bg-muted/30 p-5">
                <p className="text-sm leading-relaxed text-muted-foreground">
                  <span className="font-semibold text-foreground">Cara kami bekerja:</span> setiap tugas
                  memiliki pemilik dan bukti penyelesaian; setiap rilis melewati verifikasi; setiap
                  keputusan penting tercatat.
                </p>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-1">
              {principles.map((principle) => (
                <Card
                  key={principle.title}
                  className="flex flex-row items-start gap-4 border border-border p-6 transition-colors hover:border-primary/40"
                >
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <principle.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="font-semibold">{principle.title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      {principle.description}
                    </p>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Layanan */}
      <section id="layanan" className="border-b border-border bg-muted/20">
        <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
          <div className="mx-auto mb-14 max-w-2xl text-center">
            <Badge variant="secondary" className="mb-4">
              Layanan
            </Badge>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Yang kami kerjakan</h2>
            <p className="mt-4 text-muted-foreground">
              Dari konsep sampai operasional — dengan tim yang sama yang bertanggung jawab atas hasilnya.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {services.map((service) => (
              <Card
                key={service.title}
                className="flex flex-col gap-4 border border-border p-6 transition-colors hover:border-primary/40"
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <service.icon className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-semibold">{service.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {service.description}
                  </p>
                </div>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Tim */}
      <section id="tim" className="border-b border-border">
        <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
          <div className="mx-auto mb-14 max-w-2xl text-center">
            <Badge variant="secondary" className="mb-4">
              Tim
            </Badge>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Orang di balik Bangkah</h2>
            <p className="mt-4 text-muted-foreground">
              Peran yang jelas, tanggung jawab yang jelas. Setiap orang bisa dihubungi langsung.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {team.map((member) => (
              <Card
                key={member.id}
                className="flex flex-col gap-4 border border-border p-6 transition-colors hover:border-primary/40"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <Avatar className="h-14 w-14 ring-1 ring-border">
                      {member.image ? (
                        <AvatarImage src={member.image} alt={member.name} />
                      ) : null}
                      <AvatarFallback className="bg-primary/10 text-primary">
                        {member.name[0]}
                      </AvatarFallback>
                    </Avatar>
                    <div>
                      <h3 className="font-semibold">{member.name}</h3>
                      <p className="text-sm text-muted-foreground">{member.role}</p>
                    </div>
                  </div>
                  <Badge variant="outline" className="shrink-0 text-[11px]">
                    {member.division}
                  </Badge>
                </div>
                <p className="text-sm leading-relaxed text-muted-foreground">{member.note}</p>
                <a
                  href={`mailto:${member.email}`}
                  className="mt-auto inline-flex items-center gap-2 text-sm text-primary hover:underline"
                >
                  <Mail className="h-3.5 w-3.5" />
                  {member.email}
                </a>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Proses */}
      <section className="border-b border-border bg-muted/20">
        <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-12 lg:grid-cols-[0.8fr_1.2fr]">
            <div>
              <Badge variant="secondary" className="mb-4">
                Cara Kerja
              </Badge>
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
                Proses yang bisa diperiksa, bukan sekadar dijanjikan.
              </h2>
              <p className="mt-4 leading-relaxed text-muted-foreground">
                Kami memecah pekerjaan menjadi tahap yang jelas. Setiap tahap punya keluaran yang bisa
                dilihat, diuji, dan disetujui sebelum lanjut.
              </p>
              <a
                href="#kontak"
                className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
              >
                Diskusikan kebutuhan Anda
                <ArrowRight className="h-4 w-4" />
              </a>
            </div>

            <div className="relative">
              <div className="absolute bottom-2 left-[15px] top-2 w-px bg-border sm:left-[19px]" />
              <div className="flex flex-col gap-6">
                {process.map((item) => (
                  <div key={item.step} className="relative flex gap-5">
                    <div className="relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-primary/40 bg-background text-[11px] font-bold text-primary sm:h-10 sm:w-10 sm:text-xs">
                      {item.step}
                    </div>
                    <div className="pt-0.5">
                      <h3 className="font-semibold">{item.title}</h3>
                      <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                        {item.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Proyek */}
      <section id="proyek" className="border-b border-border">
        <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
          <div className="mx-auto mb-14 max-w-2xl text-center">
            <Badge variant="secondary" className="mb-4">
              Proyek
            </Badge>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Yang sedang kami bangun</h2>
            <p className="mt-4 text-muted-foreground">
              Produk internal dan platform yang menjadi fondasi cara kerja Bangkah.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
            {projects.map((project) => (
              <Card key={project.title} className="flex flex-col gap-4 border border-border p-6">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                    {project.tag === "Desktop + Backend" ? (
                      <Building2 className="h-5 w-5" />
                    ) : project.tag === "Web Platform" ? (
                      <Braces className="h-5 w-5" />
                    ) : (
                      <Workflow className="h-5 w-5" />
                    )}
                  </div>
                  <Badge variant={project.status === "Live" ? "default" : "outline"}>
                    {project.status}
                  </Badge>
                </div>
                <h3 className="font-semibold">{project.title}</h3>
                <p className="flex-1 text-sm leading-relaxed text-muted-foreground">
                  {project.description}
                </p>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">{project.tag}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-b border-border bg-gradient-to-br from-primary/10 via-background to-accent/5">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-6 px-4 py-14 sm:px-6 md:flex-row md:items-center lg:px-8">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Rocket className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
                Punya masalah yang layak diselesaikan?
              </h2>
              <p className="mt-2 text-muted-foreground">
                Ceritakan konteksnya. Kami akan menjawab dengan jujur — termasuk jika kami bukan tim yang tepat.
              </p>
            </div>
          </div>
          <a
            href="#kontak"
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Hubungi Bangkah
            <ArrowRight className="h-4 w-4" />
          </a>
        </div>
      </section>

      {/* Kontak */}
      <section id="kontak" className="border-b border-border">
        <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-12 lg:grid-cols-[0.9fr_1.1fr]">
            <div>
              <Badge variant="secondary" className="mb-4">
                Kontak
              </Badge>
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Mari berdiskusi</h2>
              <p className="mt-4 max-w-lg leading-relaxed text-muted-foreground">
                Untuk kerja sama, pertanyaan, atau sekadar berkenalan — kirim pesan dan tim kami akan
                membalas melalui email.
              </p>

              <div className="mt-8 flex flex-col gap-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                    <Mail className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">Email</p>
                    <a
                      href="mailto:owner@bangkah.web.id"
                      className="text-sm text-primary hover:underline"
                    >
                      owner@bangkah.web.id
                    </a>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                    <MapPin className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">Lokasi</p>
                    <p className="text-sm text-muted-foreground">Indonesia · bekerja remote</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                    <Building2 className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">Perusahaan</p>
                    <p className="text-sm text-muted-foreground">Bangkah · bangkah.web.id</p>
                  </div>
                </div>
              </div>

              <div className="mt-8 rounded-xl border border-border bg-muted/20 p-5">
                <p className="text-sm font-medium">Untuk tim internal</p>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                  Alamat email setiap anggota tim tercantum di kartu profil. Portal file dan layanan
                  internal tersedia di jaringan kantor.
                </p>
              </div>
            </div>

            <Card className="border border-border p-6 sm:p-8">
              <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="flex flex-col gap-2">
                    <label htmlFor="name" className="text-sm font-medium">
                      Nama <span className="text-destructive">*</span>
                    </label>
                    <input
                      id="name"
                      name="name"
                      type="text"
                      required
                      maxLength={120}
                      className="flex h-10 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                      placeholder="Nama Anda"
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <label htmlFor="email" className="text-sm font-medium">
                      Email <span className="text-destructive">*</span>
                    </label>
                    <input
                      id="email"
                      name="email"
                      type="email"
                      required
                      maxLength={200}
                      className="flex h-10 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                      placeholder="email@contoh.com"
                    />
                  </div>
                </div>
                <div className="flex flex-col gap-2">
                  <label htmlFor="company" className="text-sm font-medium">
                    Perusahaan / organisasi
                  </label>
                  <input
                    id="company"
                    name="company"
                    type="text"
                    maxLength={160}
                    className="flex h-10 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    placeholder="Opsional"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <label htmlFor="message" className="text-sm font-medium">
                    Pesan <span className="text-destructive">*</span>
                  </label>
                  <textarea
                    id="message"
                    name="message"
                    required
                    minLength={10}
                    maxLength={5000}
                    className="flex min-h-[140px] w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    placeholder="Ceritakan kebutuhan atau konteks Anda..."
                  />
                </div>

                {/* Honeypot — tidak terlihat oleh manusia */}
                <div className="absolute left-[-9999px] top-auto h-px w-px overflow-hidden" aria-hidden="true">
                  <label htmlFor="website">Website</label>
                  <input id="website" name="website" type="text" tabIndex={-1} autoComplete="off" />
                </div>

                {status === "success" ? (
                  <div className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-3 text-sm">
                    Pesan terkirim. Terima kasih — kami akan membalas melalui email.
                  </div>
                ) : null}
                {status === "error" ? (
                  <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
                    {errorMessage || "Pesan belum dapat dikirim. Coba lagi sebentar lagi."}
                  </div>
                ) : null}

                <div className="flex items-center justify-between gap-4 pt-1">
                  <p className="text-xs text-muted-foreground">
                    Dengan mengirim pesan, Anda setuju kami menghubungi Anda melalui email.
                  </p>
                  <button
                    type="submit"
                    disabled={status === "sending"}
                    className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {status === "sending" ? "Mengirim..." : "Kirim pesan"}
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </form>
            </Card>
          </div>
        </div>
      </section>
    </div>
  );
}
