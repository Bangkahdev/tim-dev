import PostalMime from "postal-mime";

interface R2Bucket {
  put(
    key: string,
    value: ArrayBuffer | ReadableStream | string,
    options?: { httpMetadata?: { contentType?: string }; customMetadata?: Record<string, string> },
  ): Promise<unknown>;
  get(key: string): Promise<{
    body: ReadableStream;
    httpMetadata?: { contentType?: string };
    customMetadata?: Record<string, string>;
    size: number;
  } | null>;
  delete(key: string): Promise<void>;
  list(options?: {
    prefix?: string;
    limit?: number;
    cursor?: string;
  }): Promise<{ objects: Array<{ key: string; size: number; uploaded: Date }>; truncated: boolean; cursor?: string }>;
}

interface D1PreparedStatement {
  bind(...values: unknown[]): D1PreparedStatement;
  first<T = Record<string, unknown>>(): Promise<T | null>;
  all<T = Record<string, unknown>>(): Promise<{ results?: T[] }>;
  run(): Promise<unknown>;
}

interface D1Database {
  prepare(query: string): D1PreparedStatement;
}

interface ForwardableEmailMessage {
  readonly from: string;
  readonly to: string;
  readonly headers: Headers;
  readonly raw: ReadableStream;
  readonly rawSize: number;
  forward(to: string): Promise<void>;
  setReject(reason: string): void;
}

interface ExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
}

interface Env {
  MAIL_DB: D1Database;
  MAIL_BUCKET: R2Bucket;
  MAIL_DOMAIN: string;
  MAIL_API_TOKEN: string;
  FORWARD_TO?: string;
  BANGKAH_WEBHOOK?: string;
  BANGKAH_WEBHOOK_TOKEN?: string;
  RESEND_API_KEY?: string;
  RESEND_FROM?: string;
}

const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

interface StoredMessage {
  id: string;
  mailbox: string;
  to_addr: string;
  from_addr: string;
  subject: string;
  text_body: string;
  html_body: string;
  attachments_json: string;
  raw_key: string;
  size: number;
  received_at: string;
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function stripHtml(html: string): string {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function safeEqual(left: string, right: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const a = await crypto.subtle.digest("SHA-256", encoder.encode(left));
  const b = await crypto.subtle.digest("SHA-256", encoder.encode(right));
  const av = new Uint8Array(a);
  const bv = new Uint8Array(b);
  let diff = av.length ^ bv.length;
  for (let i = 0; i < Math.min(av.length, bv.length); i += 1) {
    diff |= av[i] ^ bv[i];
  }
  return diff === 0;
}

function basicCredentials(request: Request): { user: string; password: string } | null {
  const header = request.headers.get("authorization") || "";
  if (!header.startsWith("Basic ")) return null;
  try {
    const decoded = atob(header.slice(6));
    const separator = decoded.indexOf(":");
    if (separator < 0) return null;
    return { user: decoded.slice(0, separator), password: decoded.slice(separator + 1) };
  } catch {
    return null;
  }
}

async function isAuthorized(request: Request, env: Env): Promise<boolean> {
  if (!env.MAIL_API_TOKEN) return false;
  const bearer = request.headers.get("authorization") || "";
  if (bearer.startsWith("Bearer ") && (await safeEqual(bearer.slice(7), env.MAIL_API_TOKEN))) {
    return true;
  }
  const basic = basicCredentials(request);
  return Boolean(basic && (await safeEqual(basic.password, env.MAIL_API_TOKEN)));
}

async function handleEmail(message: ForwardableEmailMessage, env: Env, ctx: ExecutionContext): Promise<void> {
  const id = crypto.randomUUID();
  const receivedAt = new Date().toISOString();
  const to = (message.to || "").trim().toLowerCase();
  const from = (message.from || "").trim().toLowerCase();
  const mailbox = to.split("@")[0] || "unknown";

  const raw = await new Response(message.raw).arrayBuffer();
  let parsed: Awaited<ReturnType<typeof PostalMime.parse>> | null = null;
  try {
    parsed = await PostalMime.parse(raw);
  } catch (error) {
    console.error("Gagal mem-parsing email", error);
  }

  const subject = parsed?.subject?.trim() || "(tanpa subjek)";
  const textBody = parsed?.text?.trim() || stripHtml(parsed?.html || "") || "";
  const htmlBody = parsed?.html || "";
  const attachments = (parsed?.attachments || []).map((attachment) => ({
    filename: attachment.filename || "attachment",
    mimeType: attachment.mimeType || "application/octet-stream",
    size: attachment.content instanceof ArrayBuffer ? attachment.content.byteLength : 0,
  }));

  const rawKey = `messages/${receivedAt.slice(0, 10)}/${id}.eml`;
  let storedRawKey = rawKey;

  try {
    await env.MAIL_BUCKET.put(rawKey, raw, {
      httpMetadata: { contentType: "message/rfc822" },
      customMetadata: { mailbox, from, subject: subject.slice(0, 200) },
    });
  } catch (error) {
    console.error("Gagal menyimpan raw email ke R2", error);
    storedRawKey = "";
  }

  await env.MAIL_DB.prepare(
    `INSERT INTO messages
      (id, mailbox, to_addr, from_addr, subject, text_body, html_body, attachments_json, raw_key, size, received_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      id,
      mailbox,
      to,
      from,
      subject.slice(0, 500),
      textBody.slice(0, 100000),
      htmlBody.slice(0, 200000),
      JSON.stringify(attachments),
      storedRawKey,
      raw.byteLength,
      receivedAt,
    )
    .run();

  if (env.FORWARD_TO) {
    try {
      await message.forward(env.FORWARD_TO);
    } catch (error) {
      console.error("Gagal meneruskan email", error);
    }
  }

  if (env.BANGKAH_WEBHOOK) {
    ctx.waitUntil(
      fetch(env.BANGKAH_WEBHOOK, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...(env.BANGKAH_WEBHOOK_TOKEN
            ? { authorization: `Bearer ${env.BANGKAH_WEBHOOK_TOKEN}` }
            : {}),
        },
        body: JSON.stringify({
          id,
          mailbox,
          to,
          from,
          subject,
          text: textBody.slice(0, 20000),
          received_at: receivedAt,
          attachments,
        }),
      }).catch((error) => console.error("Webhook backend gagal", error)),
    );
  }
}

async function handleList(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const mailbox = (url.searchParams.get("mailbox") || "").trim().toLowerCase();
  const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || 50), 1), 200);

  const statement = mailbox
    ? env.MAIL_DB.prepare(
        "SELECT id, mailbox, to_addr, from_addr, subject, size, received_at FROM messages WHERE mailbox = ? ORDER BY received_at DESC LIMIT ?",
      ).bind(mailbox, limit)
    : env.MAIL_DB.prepare(
        "SELECT id, mailbox, to_addr, from_addr, subject, size, received_at FROM messages ORDER BY received_at DESC LIMIT ?",
      ).bind(limit);

  const result = await statement.all();
  return json({ messages: result.results ?? [] });
}

async function handleDetail(id: string, env: Env): Promise<Response> {
  const message = await env.MAIL_DB.prepare("SELECT * FROM messages WHERE id = ?").bind(id).first<StoredMessage>();
  if (!message) return json({ error: "Pesan tidak ditemukan." }, 404);
  return json({
    ...message,
    attachments: JSON.parse(message.attachments_json || "[]"),
  });
}

async function handleRaw(id: string, env: Env): Promise<Response> {
  const message = await env.MAIL_DB.prepare("SELECT raw_key, subject FROM messages WHERE id = ?")
    .bind(id)
    .first<{ raw_key: string; subject: string }>();
  if (!message || !message.raw_key) return json({ error: "Raw email tidak tersedia." }, 404);

  const object = await env.MAIL_BUCKET.get(message.raw_key);
  if (!object) return json({ error: "Raw email tidak ditemukan." }, 404);

  return new Response(object.body, {
    headers: {
      "content-type": "message/rfc822",
      "content-disposition": `attachment; filename="${id}.eml"`,
    },
  });
}

async function handleDelete(id: string, env: Env): Promise<Response> {
  const message = await env.MAIL_DB.prepare("SELECT raw_key FROM messages WHERE id = ?")
    .bind(id)
    .first<{ raw_key: string }>();
  if (!message) return json({ error: "Pesan tidak ditemukan." }, 404);

  if (message.raw_key) {
    await env.MAIL_BUCKET.delete(message.raw_key).catch(() => undefined);
  }
  await env.MAIL_DB.prepare("DELETE FROM messages WHERE id = ?").bind(id).run();
  return json({ ok: true });
}

async function handleSend(request: Request, env: Env): Promise<Response> {
  if (!env.RESEND_API_KEY) {
    return json(
      {
        error:
          "Pengiriman keluar belum aktif. Tambahkan secret RESEND_API_KEY dan verifikasi domain bangkah.web.id di Resend.",
      },
      501,
    );
  }

  let payload: Record<string, unknown>;
  try {
    payload = (await request.json()) as Record<string, unknown>;
  } catch {
    return json({ error: "JSON tidak valid." }, 400);
  }

  const from = String(payload.from || env.RESEND_FROM || "owner@bangkah.web.id");
  const to = String(payload.to || "");
  const subject = String(payload.subject || "");
  const text = String(payload.text || "");
  const html = String(payload.html || "");

  if (!from.endsWith(`@${env.MAIL_DOMAIN}`)) {
    return json({ error: `Pengirim harus memakai domain @${env.MAIL_DOMAIN}.` }, 400);
  }
  if (!to.includes("@") || !subject || (!text && !html)) {
    return json({ error: "Field to, subject, dan text/html wajib diisi." }, 400);
  }

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.RESEND_API_KEY}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ from, to: [to], subject, text, html }),
  });

  const result = await response.json().catch(() => ({}));
  return json(result, response.status);
}

function inboxHtml(): string {
  return `<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Mail · Bangkah</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%2346c08a'/%3E%3Ctext x='32' y='45' text-anchor='middle' font-size='40' font-family='sans-serif' font-weight='bold' fill='%2308130d'%3EB%3C/text%3E%3C/svg%3E" />
<style>
  :root { color-scheme: dark; --bg:#0f1418; --panel:#131b21; --border:#26333d; --text:#dfe7ec; --muted:#8fa2ae; --primary:#46c08a; --danger:#e5726f; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; background:var(--bg); color:var(--text); }
  header { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 22px; border-bottom:1px solid var(--border); background:rgba(15,20,24,.92); position:sticky; top:0; z-index:5; }
  .brand { display:flex; align-items:center; gap:10px; font-weight:600; }
  .logo { width:34px; height:34px; border-radius:9px; background:var(--primary); color:#08130d; display:grid; place-items:center; font-weight:800; }
  .brand small { display:block; color:var(--muted); font-weight:400; font-size:11px; letter-spacing:.14em; text-transform:uppercase; }
  .btn { border:1px solid var(--border); background:#18222a; color:var(--text); border-radius:8px; padding:8px 13px; font-size:13px; cursor:pointer; }
  .btn:hover { border-color:#3a4b58; }
  .btn.primary { background:var(--primary); color:#08130d; border-color:transparent; font-weight:600; }
  .btn.danger { color:var(--danger); }
  main { max-width:1200px; margin:0 auto; padding:22px; }
  .login { max-width:420px; margin:10vh auto; background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:26px; }
  .login h1 { margin:0 0 6px; font-size:22px; }
  .login p { margin:0 0 18px; color:var(--muted); font-size:14px; line-height:1.5; }
  .field { display:flex; flex-direction:column; gap:6px; margin-bottom:14px; }
  label { font-size:13px; color:var(--muted); }
  input, select, textarea { width:100%; border:1px solid var(--border); background:#0b1115; color:var(--text); border-radius:8px; padding:10px 12px; font-size:14px; font-family:inherit; }
  input:focus, select:focus, textarea:focus { outline:2px solid rgba(70,192,138,.35); border-color:var(--primary); }
  .error { color:var(--danger); font-size:13px; min-height:18px; }
  .toolbar { display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; margin-bottom:16px; }
  .toolbar .filters { display:flex; gap:8px; flex-wrap:wrap; }
  .layout { display:grid; grid-template-columns: 360px 1fr; gap:16px; min-height:65vh; }
  .panel { background:var(--panel); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
  .list { max-height:68vh; overflow:auto; }
  .item { padding:13px 15px; border-bottom:1px solid var(--border); cursor:pointer; }
  .item:hover, .item.active { background:#1a252d; }
  .item .top { display:flex; justify-content:space-between; gap:10px; font-size:13px; }
  .item .from { font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .item .time { color:var(--muted); font-size:11px; white-space:nowrap; }
  .item .subject { font-size:13px; margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .item .mailbox { display:inline-block; margin-top:6px; font-size:10px; color:var(--primary); text-transform:uppercase; letter-spacing:.08em; }
  .reader { padding:20px 22px; max-height:68vh; overflow:auto; }
  .reader h2 { margin:0 0 10px; font-size:20px; }
  .meta { display:grid; grid-template-columns:auto 1fr; gap:4px 14px; font-size:13px; color:var(--muted); margin-bottom:16px; }
  .meta strong { color:var(--text); font-weight:500; }
  .body { white-space:pre-wrap; overflow-wrap:anywhere; font-size:14px; line-height:1.65; border-top:1px solid var(--border); padding-top:16px; }
  .body-html { display:block; width:100%; min-height:420px; border:0; border-top:1px solid var(--border); background:#fff; color:#111; border-radius:8px; }
  .empty { color:var(--muted); text-align:center; padding:50px 20px; font-size:14px; }
  .status { font-size:12px; color:var(--muted); }
  .banner { border:1px solid #345c49; background:rgba(70,192,138,.08); color:#bfe8d5; padding:10px 12px; border-radius:8px; font-size:12px; margin-bottom:14px; line-height:1.5; }
  @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .list { max-height:40vh; } .reader { max-height:none; } }
</style>
</head>
<body>
<header>
  <div class="brand"><div class="logo">B</div><div>Bangkah Mail<small>bangkah.web.id</small></div></div>
  <div style="display:flex;gap:8px;align-items:center">
    <span id="status" class="status"></span>
    <button class="btn" id="refresh" hidden>Muat ulang</button>
    <button class="btn" id="logout" hidden>Keluar</button>
  </div>
</header>
<main>
  <section id="loginView" class="login">
    <h1>Inbox perusahaan</h1>
    <p>Masuk dengan token akses perusahaan. Semua email ke alamat @bangkah.web.id diarsipkan di sini.</p>
    <div class="field">
      <label for="token">Access token</label>
      <input id="token" type="password" autocomplete="current-password" placeholder="Tempel token perusahaan" />
    </div>
    <div id="loginError" class="error"></div>
    <button id="loginBtn" class="btn primary" style="width:100%">Masuk</button>
  </section>

  <section id="inboxView" hidden>
    <div id="configBanner" class="banner">Email keluar belum aktif. Tambahkan secret <strong>RESEND_API_KEY</strong> dan verifikasi domain untuk mengirim dari alamat perusahaan.</div>
    <div class="toolbar">
      <div class="filters">
        <select id="mailbox">
          <option value="">Semua alamat</option>
          <option value="owner">owner@</option>
          <option value="arman">arman@</option>
          <option value="sinta">sinta@</option>
          <option value="raka">raka@</option>
          <option value="bima">bima@</option>
          <option value="naya">naya@</option>
          <option value="dira">dira@</option>
          <option value="tika">tika@</option>
          <option value="mira">mira@</option>
          <option value="team">team@</option>
          <option value="contact">contact@</option>
        </select>
        <button class="btn" id="load">Tampilkan</button>
      </div>
      <span id="count" class="status"></span>
    </div>
    <div class="layout">
      <div class="panel"><div id="list" class="list"><div class="empty">Belum ada email.</div></div></div>
      <div class="panel"><div id="reader" class="reader"><div class="empty">Pilih email untuk membaca.</div></div></div>
    </div>
  </section>
</main>
<script>
  const state = { token: localStorage.getItem("bangkah_mail_token") || "", messages: [], active: null };
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtTime = (value) => { try { return new Date(value).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }); } catch { return value; } };
  const authHeaders = () => ({ authorization: "Bearer " + state.token });

  async function api(path, options = {}) {
    const response = await fetch(path, { ...options, headers: { ...(options.headers || {}), ...authHeaders() } });
    if (response.status === 401) { showLogin("Sesi berakhir. Masuk kembali."); throw new Error("Unauthorized"); }
    if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.error || "Permintaan gagal"); }
    return response;
  }

  function showLogin(message = "") {
    $("loginView").hidden = false;
    $("inboxView").hidden = true;
    $("refresh").hidden = true;
    $("logout").hidden = true;
    $("loginError").textContent = message;
  }

  function showInbox() {
    $("loginView").hidden = true;
    $("inboxView").hidden = false;
    $("refresh").hidden = false;
    $("logout").hidden = false;
    $("configBanner").hidden = false;
  }

  async function loadMessages() {
    const mailbox = $("mailbox").value;
    $("status").textContent = "Memuat...";
    try {
      const response = await api("/api/messages?limit=100" + (mailbox ? "&mailbox=" + encodeURIComponent(mailbox) : ""));
      const data = await response.json();
      state.messages = data.messages || [];
      renderList();
      $("status").textContent = "";
      $("count").textContent = state.messages.length + " pesan";
    } catch (error) {
      $("status").textContent = error.message;
    }
  }

  function renderList() {
    const list = $("list");
    if (!state.messages.length) {
      list.innerHTML = '<div class="empty">Tidak ada email pada kotak ini.</div>';
      return;
    }
    list.innerHTML = state.messages.map((message) => (
      '<div class="item ' + (state.active === message.id ? "active" : "") + '" data-id="' + esc(message.id) + '">'
      + '<div class="top"><span class="from">' + esc(message.from_addr) + '</span><span class="time">' + esc(fmtTime(message.received_at)) + "</span></div>"
      + '<div class="subject">' + esc(message.subject) + "</div>"
      + '<span class="mailbox">' + esc(message.to_addr) + "</span>"
      + "</div>"
    )).join("");
    list.querySelectorAll(".item").forEach((element) => element.addEventListener("click", () => openMessage(element.dataset.id)));
  }

  async function openMessage(id) {
    state.active = id;
    renderList();
    $("reader").innerHTML = '<div class="empty">Memuat pesan...</div>';
    try {
      const response = await api("/api/messages/" + encodeURIComponent(id));
      const message = await response.json();
      const body = message.html_body && message.html_body.trim()
        ? '<iframe class="body body-html" sandbox referrerpolicy="no-referrer" srcdoc="' + esc(message.html_body) + '"></iframe>'
        : "<div class='body'>" + esc(message.text_body || "(tanpa isi)") + "</div>";
      $("reader").innerHTML = (
        '<div style="display:flex;justify-content:space-between;gap:12px;align-items:start">'
        + "<h2>" + esc(message.subject) + "</h2>"
        + '<div style="display:flex;gap:8px;flex-shrink:0">'
        + '<a class="btn" href="/api/messages/' + encodeURIComponent(id) + '/raw">Unduh .eml</a>'
        + '<button class="btn danger" id="deleteBtn">Hapus</button>'
        + "</div>"
        + "</div>"
        + '<div class="meta">'
        + "<span>Dari</span><strong>" + esc(message.from_addr) + "</strong>"
        + "<span>Kepada</span><strong>" + esc(message.to_addr) + "</strong>"
        + "<span>Waktu</span><strong>" + esc(fmtTime(message.received_at)) + "</strong>"
        + "<span>Lampiran</span><strong>" + (message.attachments || []).length + " berkas</strong>"
        + "</div>"
        + '<div class="body html">' + body + "</div>"
      );
      $("deleteBtn").addEventListener("click", async () => {
        if (!confirm("Hapus email ini dari arsip?")) return;
        await api("/api/messages/" + encodeURIComponent(id), { method: "DELETE" });
        state.active = null;
        $("reader").innerHTML = '<div class="empty">Email dihapus.</div>';
        await loadMessages();
      });
    } catch (error) {
      $("reader").innerHTML = '<div class="empty">' + esc(error.message) + "</div>";
    }
  }

  async function login() {
    const token = $("token").value.trim();
    if (!token) { showLogin("Token wajib diisi."); return; }
    state.token = token;
    try {
      const response = await fetch("/api/messages?limit=1", { headers: { authorization: "Bearer " + token } });
      if (!response.ok) throw new Error("Token tidak valid.");
      localStorage.setItem("bangkah_mail_token", token);
      showInbox();
      await loadMessages();
    } catch (error) {
      state.token = "";
      showLogin(error.message);
    }
  }

  $("loginBtn").addEventListener("click", login);
  $("token").addEventListener("keydown", (event) => { if (event.key === "Enter") login(); });
  $("load").addEventListener("click", loadMessages);
  $("refresh").addEventListener("click", loadMessages);
  $("logout").addEventListener("click", () => { localStorage.removeItem("bangkah_mail_token"); state.token = ""; state.messages = []; state.active = null; showLogin(); });

  if (state.token) { showInbox(); loadMessages(); } else { showLogin(); }
</script>
</body>
</html>`;
}

async function handleRequest(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname === "/api/health") {
    return json({ status: "ok", service: "bangkah-mail", domain: env.MAIL_DOMAIN });
  }

  if (url.pathname === "/" && request.method === "GET") {
    return new Response(inboxHtml(), { headers: { "content-type": "text/html; charset=utf-8" } });
  }

  if (!(await isAuthorized(request, env))) {
    return new Response("Unauthorized", {
      status: 401,
      headers: { "www-authenticate": 'Basic realm="Bangkah Mail", charset="UTF-8"' },
    });
  }

  if (url.pathname === "/api/messages" && request.method === "GET") {
    return handleList(request, env);
  }

  const detailMatch = url.pathname.match(/^\/api\/messages\/([0-9a-f-]+)$/i);
  if (detailMatch && request.method === "GET") {
    return handleDetail(detailMatch[1], env);
  }
  if (detailMatch && request.method === "DELETE") {
    return handleDelete(detailMatch[1], env);
  }

  const rawMatch = url.pathname.match(/^\/api\/messages\/([0-9a-f-]+)\/raw$/i);
  if (rawMatch && request.method === "GET") {
    return handleRaw(rawMatch[1], env);
  }

  if (url.pathname === "/api/send" && request.method === "POST") {
    return handleSend(request, env);
  }

  return json({ error: "Not found" }, 404);
}

export default {
  async email(message: ForwardableEmailMessage, env: Env, ctx: ExecutionContext): Promise<void> {
    await handleEmail(message, env, ctx);
  },
  async fetch(request: Request, env: Env): Promise<Response> {
    return handleRequest(request, env);
  },
};
