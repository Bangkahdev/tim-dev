// Tipe minimal untuk bindings Cloudflare (tanpa paket @cloudflare/workers-types,
// karena disk exFAT tidak mendukung instalasi .bin symlink npm).
// Tidak berpengaruh pada build produksi wrangler (esbuild mengabaikan types).

declare type Fetcher = { fetch(input: RequestInfo, init?: RequestInit): Promise<Response> };

declare interface D1Result<T = Record<string, unknown>> {
  results?: T[];
  success?: boolean;
  meta?: Record<string, unknown>;
}

declare interface D1PreparedStatement {
  bind(...values: unknown[]): D1PreparedStatement;
  first<T = Record<string, unknown>>(): Promise<T | null>;
  all<T = Record<string, unknown>>(): Promise<D1Result<T>>;
  run(): Promise<D1Result>;
}

declare interface D1Database {
  prepare(query: string): D1PreparedStatement;
  batch(statements: D1PreparedStatement[]): Promise<D1Result[]>;
}
