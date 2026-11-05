import { defineConfig } from "cf/config";

export default defineConfig({
  worker: {
    name: "bangkah-site",
    compatibilityDate: "2026-11-04",
    domains: ["bangkah.web.id", "www.bangkah.web.id"],
    observability: { enabled: true },
  },
});
