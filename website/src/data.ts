export const navItems = [
  { label: "Beranda", href: "#beranda" },
  { label: "Tentang", href: "#tentang" },
  { label: "Kapabilitas", href: "#kapabilitas" },
  { label: "Tim", href: "#tim" },
  { label: "Kontak", href: "#kontak" },
]

export const stats = [
  { value: "7", label: "Spesialis inti" },
  { value: "4", label: "Disiplin kerja" },
  { value: "1", label: "Markas di Jakarta" },
  { value: "100%", label: "Keputusan tercatat" },
]

export const services = [
  {
    id: "produk",
    number: "01",
    title: "Product Engineering",
    summary:
      "Merancang dan membangun produk digital dari nol: riset singkat, prototipe cepat, lalu rilis yang bisa dipakai.",
    points: [
      "Discovery dan pemetaan alur kerja",
      "Antarmuka produk yang tenang dan jelas",
      "Rilis bertahap dengan umpan balik nyata",
    ],
    stack: ["TypeScript", "React", "Godot", "Figma"],
    image: "/images/office-frontend.png",
    alt: "Studio frontend dan desain di markas Bangkah",
  },
  {
    id: "platform",
    number: "02",
    title: "Platform & API",
    summary:
      "Membangun fondasi yang tidak perlu sering disentuh: API yang rapi, data yang konsisten, dan integrasi yang aman.",
    points: [
      "Desain API dan kontrak data",
      "Integrasi layanan internal dan pihak ketiga",
      "Observability, backup, dan pemulihan",
    ],
    stack: ["Python", "PostgreSQL", "Cloudflare", "REST"],
    image: "/images/office-api.png",
    alt: "Laboratorium API dan infrastruktur di markas Bangkah",
  },
  {
    id: "kualitas",
    number: "03",
    title: "Quality & Reliability",
    summary:
      "Kualitas bukan tahap terakhir. Kami menguji lebih awal, mencatat bukti, dan menjaga rilis tetap bisa dipertanggungjawabkan.",
    points: [
      "Strategi pengujian yang proporsional",
      "Otomasi regresi dan audit rilis",
      "Pemantauan setelah rilis",
    ],
    stack: ["Playwright", "Pytest", "CI/CD", "Audit log"],
    image: "/images/office-qa.png",
    alt: "Laboratorium QA di markas Bangkah",
  },
  {
    id: "ai",
    number: "04",
    title: "AI Workflow Design",
    summary:
      "Menyusun cara kerja manusia dan AI dalam satu sistem: peran yang jelas, persetujuan manusia, dan jejak keputusan.",
    points: [
      "Pemetaan tugas yang layak diotomasi",
      "Approval dan batas kewenangan",
      "Dokumentasi dan evaluasi berkelanjutan",
    ],
    stack: ["Agent workflow", "Human-in-the-loop", "Policy", "Audit"],
    image: "/images/office-leadership.png",
    alt: "Ruang leadership di markas Bangkah",
  },
]

export const principles = [
  {
    title: "Kantor sebagai antarmuka",
    body: "Kami bekerja di satu markas yang bisa dijelajahi. Konteks tidak hilang di antara rapat, dokumen, dan keputusan.",
  },
  {
    title: "Bukti sebelum selesai",
    body: "Setiap pekerjaan ditutup dengan bukti: commit, laporan QA, build, atau verifikasi yang bisa diperiksa.",
  },
  {
    title: "Manusia tetap memutuskan",
    body: "Sistem boleh mengusulkan dan menyiapkan. Aksi eksternal menunggu persetujuan manusia yang tercatat.",
  },
  {
    title: "Sistem yang bisa diaudit",
    body: "Payload persetujuan dikunci dengan hash, perubahan dicatat, dan riwayat tidak ditulis ulang diam-diam.",
  },
]

export const team = [
  {
    name: "Arman",
    role: "Lead Manager",
    focus: "Arah produk, prioritas sprint, dan keputusan rilis.",
    initials: "AR",
    tone: "bg-[#dbe5da] text-[#2f4a3f]",
  },
  {
    name: "Sinta",
    role: "COO / Project Manager",
    focus: "Operasi harian, ritme tim, dan koordinasi lintas disiplin.",
    initials: "SI",
    tone: "bg-[#e8dfe4] text-[#5b4652]",
  },
  {
    name: "Raka",
    role: "System Architect",
    focus: "Arsitektur sistem, batas layanan, dan keputusan teknis jangka panjang.",
    initials: "RA",
    tone: "bg-[#dce5ec] text-[#38536a]",
  },
  {
    name: "Dira",
    role: "Frontend Developer",
    focus: "Antarmuka produk, design system, dan detail interaksi.",
    initials: "DI",
    tone: "bg-[#eee2d8] text-[#7a5139]",
  },
  {
    name: "Tika",
    role: "QA Engineer",
    focus: "Strategi pengujian, otomasi regresi, dan audit kualitas rilis.",
    initials: "TI",
    tone: "bg-[#dfe8df] text-[#395c42]",
  },
  {
    name: "Bima",
    role: "Backend Developer",
    focus: "Layanan inti, data, dan integrasi yang stabil.",
    initials: "BI",
    tone: "bg-[#dfe6ea] text-[#3f5666]",
  },
  {
    name: "Naya",
    role: "API Specialist",
    focus: "Kontrak API, gateway, dan keterhubungan antar sistem.",
    initials: "NA",
    tone: "bg-[#eee6d4] text-[#705a32]",
  },
  {
    name: "Mira",
    role: "Reception",
    focus: "Titik masuk markas, tamu, dan alur check-in.",
    initials: "MI",
    tone: "bg-[#e6e3d6] text-[#4f5545]",
  },
]

export const gallery = [
  {
    src: "/images/office-exterior.png",
    alt: "Fasad markas Bangkah",
    title: "Markas",
    detail: "Fasad selatan dan area penerimaan",
    span: "md:col-span-2 md:row-span-2",
  },
  {
    src: "/images/office-lobby.png",
    alt: "Lobi dan meja resepsionis Bangkah",
    title: "Lobi",
    detail: "Check-in, ruang tunggu, dan direktori",
  },
  {
    src: "/images/office-meeting.png",
    alt: "Ruang rapat boardroom Bangkah",
    title: "Boardroom",
    detail: "Ruang keputusan untuk tim inti",
  },
  {
    src: "/images/office-backend.png",
    alt: "Area backend engineering Bangkah",
    title: "Backend",
    detail: "Layanan, data, dan pemantauan",
  },
  {
    src: "/images/office-api.png",
    alt: "Laboratorium API Bangkah",
    title: "API Lab",
    detail: "Gateway dan topologi layanan",
  },
]

export const processSteps = [
  {
    number: "01",
    title: "Pahami dulu",
    body: "Kami memetakan masalah, pengguna, dan batasan sebelum menulis kode. Output-nya ringkas dan bisa dipakai.",
  },
  {
    number: "02",
    title: "Bangun yang penting",
    body: "Rilis kecil, sering, dan terukur. Setiap iterasi punya tujuan yang jelas dan bukti yang bisa diperiksa.",
  },
  {
    number: "03",
    title: "Jaga setelah rilis",
    body: "Pemantauan, perbaikan, dan dokumentasi berjalan sebagai bagian dari pekerjaan, bukan tambahan.",
  },
]

export const faqs = [
  {
    question: "Bagaimana Bangkah bekerja dengan klien?",
    answer:
      "Kami memulai dengan sesi pemetaan singkat, lalu menyusun lingkup kerja yang kecil dan jelas. Setiap minggu ada demo, catatan keputusan, dan daftar prioritas berikutnya.",
  },
  {
    question: "Apakah semua keputusan diambil oleh AI?",
    answer:
      "Tidak. Sistem internal kami membantu merangkum, menyiapkan, dan mengingatkan. Keputusan produk, persetujuan eksternal, dan arah perusahaan tetap dipegang manusia.",
  },
  {
    question: "Di mana tim bekerja?",
    answer:
      "Tim inti bekerja dari markas Bangkah di Jakarta dengan ritme kerja yang terdokumentasi. Kolaborasi jarak jauh dimungkinkan untuk lingkup tertentu.",
  },
  {
    question: "Bagaimana keamanan dan persetujuan ditangani?",
    answer:
      "Akses eksternal dan perubahan berisiko melewati persetujuan eksplisit. Payload persetujuan dikunci dengan hash, dan setiap aksi tercatat di audit log.",
  },
]

export const contact = {
  email: "halo@bangkah.web.id",
  location: "Jakarta, Indonesia",
  hours: "Senin–Jumat, 09.00–17.00 WIB",
  response: "Kami membalas dalam 1–2 hari kerja.",
}
