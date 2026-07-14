# HTTPS 전환 절차서 (Lightsail)

작성: 2026-07-14 · 목적: 인출 훈련 음성 모드(마이크 = 보안 컨텍스트 필수)와 focus-app 알림(Notification/Wake Lock)의 전제조건.
서버에 SSH로 접속해 위에서부터 순서대로 실행한다. 예상 소요 반나절 이내, 위험 구간은 §5의 롤백으로 복구 가능.

## 현재 상태 (전제)
- Lightsail Ubuntu, 고정 IP `43.202.142.135`
- nginx `:8001` → 퀴즈 정적(`/var/www/quiz`) + `/api/*` → `127.0.0.1:8011` (prefix 벗겨 전달)
- nginx `:80` → focus-app (`127.0.0.1:4000`)
- 둘 다 Basic Auth
- 프론트 API 호출은 전부 상대경로(`/api`) → **HTTPS 전환 후 프론트 재빌드 불필요**

## 1. 무료 도메인 (DuckDNS)

1. https://www.duckdns.org 로그인(구글 계정 가능) → 서브도메인 2개 생성:
   - `<나만의이름>-quiz.duckdns.org`
   - `<나만의이름>-focus.duckdns.org`
2. 두 도메인 모두 IP를 `43.202.142.135`로 설정.
3. 고정 IP라 갱신 크론은 불필요. (Lightsail 콘솔에서 Static IP가 인스턴스에 attach 상태인지만 확인)
4. 확인: 로컬 PC에서 `nslookup <이름>-quiz.duckdns.org` → 43.202.142.135 나오면 통과.

## 2. Lightsail 방화벽

Lightsail 콘솔 → 인스턴스 → Networking → IPv4 Firewall에 **HTTPS(TCP 443) 추가**. 기존 80·8001·22는 유지.

## 3. certbot 설치 및 nginx 준비

```bash
sudo apt update && sudo apt install -y certbot python3-certbot-nginx
```
(apt 설치는 안전 — 금지된 것은 npm install/build다.)

certbot이 도메인별 server 블록을 찾도록 `server_name`을 붙인다:

```bash
sudo nano /etc/nginx/sites-available/quiz-https
```
```nginx
server {
    listen 80;
    server_name <이름>-quiz.duckdns.org;
    # ↓ 기존 :8001 블록의 내용을 그대로 복사 (root /var/www/quiz, /api 프록시, Basic Auth 등)
    root /var/www/quiz;
    index index.html;
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;   # 기존 경로 확인 후 맞출 것
    location / { try_files $uri $uri.html $uri/ /index.html; }
    location /api/ {
        proxy_pass http://127.0.0.1:8011/;       # 끝 슬래시 = prefix 벗김 유지
        proxy_set_header Host $host;
    }
}
```
```bash
sudo nano /etc/nginx/sites-available/focus-https
```
```nginx
server {
    listen 80;
    server_name <이름>-focus.duckdns.org;
    # ↓ 기존 :80 focus 블록 내용 복사
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
    location / {
        proxy_pass http://127.0.0.1:4000;
        proxy_set_header Host $host;
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/quiz-https /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/focus-https /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```
주의: 기존 `:80` focus 블록에 `server_name`이 없으면(default) 새 블록과 충돌하지 않지만, `nginx -t`에서 default server 중복 경고가 나오면 기존 블록에 `server_name 43.202.142.135;`를 명시한다.

## 4. 인증서 발급

```bash
sudo certbot --nginx -d <이름>-quiz.duckdns.org -d <이름>-focus.duckdns.org
```
- 이메일 입력, 약관 동의.
- "Redirect HTTP → HTTPS?" 물으면 **2 (Redirect)** 선택.
- 자동 갱신은 systemd 타이머로 이미 걸림. 확인: `sudo certbot renew --dry-run`

## 5. 검증 (전부 통과해야 완료)

1. `https://<이름>-quiz.duckdns.org` — 자물쇠 표시, Basic Auth 프롬프트, 퀴즈 화면·문제 풀이(= `/api`) 정상.
2. `https://<이름>-focus.duckdns.org` — 뽀모도로 화면 정상, 타이머 동작.
3. 폰(모바일 데이터)에서도 1·2 확인 — 홈 화면 바로가기를 https 주소로 갱신.
4. 마이크 테스트: focus 도메인 아무 페이지 콘솔에서 `navigator.mediaDevices.getUserMedia({audio:true})` → 권한 팝업이 뜨면 인출 훈련 음성 모드 전제조건 충족.
5. 구주소 호환: `http://43.202.142.135:8001` 접속 시 동작이 유지되는지 확인. (원하면 이 블록에 `return 301 https://<이름>-quiz.duckdns.org$request_uri;` 한 줄로 리다이렉트 전환 — 모든 검증 통과 후에.)

**롤백**: 문제 시 `sudo rm /etc/nginx/sites-enabled/{quiz,focus}-https && sudo systemctl reload nginx` — 기존 IP 접속 경로는 건드리지 않았으므로 그대로 살아 있다.

## 6. 전환 후 정리 (당일)

- [ ] `Documents\lightsail-basic-auth.txt`에 새 https 주소 병기
- [ ] 폰·PC 북마크/홈 화면 바로가기 https로 교체
- [ ] teacherExam `CLAUDE.md` 운영 서버 섹션의 접속 주소 갱신
- [ ] focus-app `docs/개선계획.md` §4-6이 이 전환을 전제로 갱신됨 — Notification 종료 알림(P4 완전판)이 구현 가능해짐
- [ ] (선택) 8001·IP 직접 접속을 301 리다이렉트로 봉인

## 7. 이 전환이 잠금 해제하는 것

| 기능 | 이전(HTTP) | 이후(HTTPS) |
|---|---|---|
| 인출 훈련 음성 모드 (마이크/Web Speech API) | 불가 | 가능 — RECALL_SPEC 3주차 전제 충족 |
| focus-app 타이머 종료 Notification | 불가 | 가능 |
| focus-app Wake Lock (화면 꺼짐 방지) | 불가 | 가능 |
| Basic Auth 자격증명 | 평문 전송 | 암호화 |
| PWA/서비스워커 (원하면) | 불가 | 가능 |
