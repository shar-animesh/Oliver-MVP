// Path: vite.config.ts
// Description: Vite development server, admin backend proxy, and production build configuration.

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            "/api": "http://localhost:8000",
        },
    },
    build: {
        outDir: "dist",
        emptyOutDir: true,
    },
});
