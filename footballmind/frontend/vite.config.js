import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base must match the GitHub repo name so built asset paths resolve on a
// project page (https://<user>.github.io/footballmind/).
export default defineConfig({
  base: "/footballmind/",
  plugins: [react()],
});
