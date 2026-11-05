/// <reference path="./cloudflare-types.d.ts" />

interface Env {
  ASSETS: Fetcher;
  DB?: D1Database;
  ADMIN_TOKEN?: string;
  CONTACT_SALT?: string;
  NOTIFY_EMAIL?: {
    send(message: {
      from: string;
      to: string;
      subject: string;
      text?: string;
      html?: string;
    }): Promise<unknown>;
  };
  CONTACT_TO?: string;
}

const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function withSecurityHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  headers.set("x-content-type-options", "nosniff");
  headers.set("referrer-policy", "strict-origin-when-cross-origin");
  headers.set("x-frame-options", "DENY");
  headers.set("permissions-policy", "camera=(), microphone=(), geolocation=()");
  headers.set("strict-transport-security", "max-age=31536000; includeSubDomains");
  headers.set(
    "content-security-policy",
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
  );
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);
}

async function hashIp(ip: string, salt: string): Promise<string> {
  const data = new TextEncoder().encode(`${ip}:${salt}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function handleContact(request: Request, env: Env): Promise<Response> {
  if (!env.DB) {
    return json({ error: "Form kontak belum dikonfigurasi." }, 503);
  }

  const contentType = request.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return json({ error: "Format permintaan tidak didukung." }, 415);
  }

  let payload: Record<string, unknown>;
  try {
    payload = (await request.json()) as Record<string, unknown>;
  } catch {
    return json({ error: "Permintaan tidak valid." }, 400);
  }

  const name = String(payload.name ?? "").trim();
  const email = String(payload.email ?? "").trim().toLowerCase();
  const company = String(payload.company ?? "").trim();
  const message = String(payload.message ?? "").trim();
  const honeypot = String(payload.website ?? "").trim();

  // Bot terdeteksi: balas sukses tanpa menyimpan apa pun.
  if (honeypot) {
    return json({ ok: true });
  }

  if (name.length < 2 || name.length > 120) {
    return json({ error: "Nama harus antara 2 dan 120 karakter." }, 400);
  }
  if (!isValidEmail(email) || email.length > 200) {
    return json({ error: "Alamat email tidak valid." }, 400);
  }
  if (company.length > 160) {
    return json({ error: "Nama perusahaan terlalu panjang." }, 400);
  }
  if (message.length < 10 || message.length > 5000) {
    return json({ error: "Pesan harus antara 10 dan 5000 karakter." }, 400);
  }

  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  const ipHash = await hashIp(ip, env.CONTACT_SALT || "bangkah-contact");

  const recent = await env.DB.prepare(
    "SELECT COUNT(*) AS count FROM contacts WHERE ip_hash = ? AND created_at > datetime('now', '-15 minutes')",
  )
    .bind(ipHash)
    .first<{ count: number }>();

  if ((recent?.count ?? 0) >= 5) {
    return json({ error: "Terlalu banyak pesan. Coba lagi beberapa menit lagi." }, 429);
  }

  const id = crypto.randomUUID();
  const createdAt = new Date().toISOString();

  await env.DB.prepare(
    "INSERT INTO contacts (id, name, email, company, message, ip_hash, user_agent, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
  )
    .bind(id, name, email, company, message, ipHash, (request.headers.get("user-agent") || "").slice(0, 300), createdAt)
    .run();

  if (env.NOTIFY_EMAIL && env.CONTACT_TO) {
    try {
      await env.NOTIFY_EMAIL.send({
        from: "contact@bangkah.my.id",
        to: env.CONTACT_TO,
        subject: `[Website] Pesan baru dari ${name}`,
        text: [
          `Nama: ${name}`,
          `Email: ${email}`,
          `Perusahaan: ${company || "-"}`,
          "",
          message,
          "",
          `ID: ${id}`,
        ].join("\n"),
      });
    } catch (error) {
      console.error("Gagal mengirim notifikasi kontak", error);
    }
  }

  return json({ ok: true, id });
}

async function handleAdminContacts(request: Request, env: Env): Promise<Response> {
  if (!env.ADMIN_TOKEN) {
    return json({ error: "Admin endpoint tidak aktif." }, 404);
  }
  const provided = request.headers.get("authorization") || "";
  if (provided !== `Bearer ${env.ADMIN_TOKEN}`) {
    return json({ error: "Unauthorized" }, 401);
  }
  if (!env.DB) {
    return json({ error: "Database belum dikonfigurasi." }, 503);
  }

  const limit = Math.min(Number(new URL(request.url).searchParams.get("limit") || 50), 200);
  const result = await env.DB.prepare(
    "SELECT id, name, email, company, message, created_at FROM contacts ORDER BY created_at DESC LIMIT ?",
  )
    .bind(limit)
    .all();

  return json({ contacts: result.results ?? [] });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Satu domain kanonik: www diarahkan permanen ke apex.
    if (url.hostname === "www.bangkah.my.id") {
      url.hostname = "bangkah.my.id";
      return Response.redirect(url.toString(), 301);
    }

    if (url.pathname === "/api/health") {
      return json({
        status: "ok",
        company: "Bangkah",
        domain: "bangkah.my.id",
        time: new Date().toISOString(),
      });
    }

    if (url.pathname === "/api/contact") {
      if (request.method !== "POST") {
        return json({ error: "Method not allowed" }, 405);
      }
      return handleContact(request, env);
    }

    if (url.pathname === "/api/contacts") {
      return handleAdminContacts(request, env);
    }

    if (url.pathname.startsWith("/api/")) {
      return json({ error: "Not found" }, 404);
    }

    const response = await env.ASSETS.fetch(request);
    return withSecurityHeaders(response);
  },
};
