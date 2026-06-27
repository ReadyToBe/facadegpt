import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        index: "index.html",
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
  },
});
