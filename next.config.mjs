/** @type {import('next').NextConfig} */
// STATIC_EXPORT=1 builds plain HTML/JS into .next-export/ for the desktop app (desktop/README.md).
// It uses its own build folder so it never disturbs a running `npm run dev`.
const nextConfig = process.env.STATIC_EXPORT === "1" ? { output: "export", distDir: ".next-export" } : {};
export default nextConfig;
