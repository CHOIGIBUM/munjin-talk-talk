import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite 개발 서버와 React 빌드 설정입니다.
// Amplify 배포도 동일하게 npm run build를 실행해 dist 정적 파일을 생성합니다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  }
})
