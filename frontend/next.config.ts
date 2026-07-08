import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 정적 export — nginx가 out/을 직접 서빙하고 /api만 FastAPI로 프록시한다.
  // 서버 기능(SSR/route handler/이미지 최적화)에 의존하는 코드를 넣지 말 것.
  // (구 standalone 배포는 2026-07-08 폐지 — docs/IMPLEMENTATION_KICKOFF.md 참고)
  output: "export",
};

export default nextConfig;
