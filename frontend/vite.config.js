import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    // Explicit, not the default glob: Vitest's default also matches
    // *.spec.js, which would try to run the Playwright specs in e2e/
    // under jsdom and fail. Unit/component tests live next to the code
    // they cover, under src/.
    include: ['src/**/*.test.{js,jsx}'],
    css: false,
  },
})
