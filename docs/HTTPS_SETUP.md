# Lightsail HTTPS 전환 런북 (DuckDNS + Let's Encrypt)

작성 2026-08-07. 서버 43.202.142.135 (Ubuntu 22.04, Lightsail).

## 왜 도메인이 필요한가

Let's Encrypt를 포함한 공인 CA는 **IP 주소로는 인증서를 발급하지 않는다.**
따라서 `https://43.202.142.135` 는 원리적으로 불가능하고, 도메인이 반드시 있어야 한다.
DuckDNS는 무료 서브도메인을 주고 Public Suffix List에 등재되어 있어 Let's Encrypt 발급·갱신이 정상 동작한다.

## 현재 구성 (전환 전)

| 외부 포트 | 앱 | nginx 설정 파일 | 내부 백엔드 |
|---|---|---|---|
| 80 (default_server) | focus-app (뽀모도로) | `default` | `127.0.0.1:4000` |
| 3001 | eatNwrite (식비) + 자기관리 기록 API | `eatnwrite` | `127.0.0.1:3012` |
| 8001 | 임용 퀴즈 (teacherExam) | `quiz` | 정적 `/var/www/quiz` + `127.0.0.1:8011` |
| 3000 | → 8001 리다이렉트 | `quiz` | — |

systemd 서비스: `focus-app`, `eatnwrite-backend`, `quiz-backend`, `unifiedbot`

## 전환 후 목표

| 주소 | 앱 |
|---|---|
| `https://<이름>-quiz.duckdns.org` | 임용 퀴즈 |
| `https://<이름>-eat.duckdns.org` | eatNwrite + 자기관리 기록 API |
| `https://<이름>-focus.duckdns.org` | focus-app |

전부 443 포트 하나에서 `server_name`으로 분기. 인증서는 3개 도메인을 SAN으로 묶은 것 1장.

---

## ⚠️ 먼저 확인할 것 두 가지

### 1. 고정 IP(Static IP)인지 확인 — 가장 중요

Lightsail 인스턴스를 **중지했다 켜면 공인 IP가 바뀐다.** 그러면 DuckDNS 설정이 깨지고
인증서 갱신도 실패한다. 고정 IP는 인스턴스에 붙어 있는 동안 **무료**다.

Lightsail 콘솔 → **Networking** 탭 → **Static IPs**
- 이미 43.202.142.135가 목록에 있고 인스턴스에 연결되어 있으면 OK
- 없으면 **Create static IP** → 인스턴스에 attach (IP가 바뀔 수 있으니 이 작업을 먼저)

### 2. 443 포트 열기 — SSH로는 불가능, 콘솔에서만

Lightsail은 OS 방화벽과 별개로 자체 방화벽이 있다. 확인 결과 **443은 현재 차단** 상태다.

Lightsail 콘솔 → 인스턴스 → **Networking** 탭 → **IPv4 Firewall** → **Add rule**
- Application: `HTTPS`, Protocol: `TCP`, Port: `443` → Create

80은 이미 열려 있다(확인함). 인증서 발급에 필요하므로 닫지 말 것.

---

## 단계 1. DuckDNS 도메인 만들기

1. https://www.duckdns.org 접속 → GitHub/Google 등으로 로그인 (무료, 계정당 5개까지)
2. `sub domain` 칸에 이름을 넣고 **add domain** — 3개 생성:
   - `<이름>-quiz`
   - `<이름>-eat`
   - `<이름>-focus`
3. 각 도메인의 `current ip` 를 **43.202.142.135** 로 설정하고 **update ip**
4. 토큰(`token`)을 복사해 둔다 — 아래 자동 갱신 스크립트에 쓴다

전파 확인 (로컬 PC에서):

```bash
nslookup 내이름-quiz.duckdns.org
```

43.202.142.135가 나오면 다음 단계로. (보통 1분 이내)

---

## 단계 2. ACME 챌린지 경로를 Basic Auth에서 제외 ⚠️

**이 단계를 빼먹으면 인증서 발급이 반드시 실패한다.**

현재 80포트 default 서버 전체에 `auth_basic "Restricted"` 가 걸려 있어서,
Let's Encrypt가 `/.well-known/acme-challenge/...` 를 가져가려 할 때 **401**을 받는다.
(실제로 확인함: `curl http://43.202.142.135/` → 401)

서버에서:

```bash
sudo tee /etc/nginx/snippets/acme.conf > /dev/null << 'EOF'
# Let's Encrypt HTTP-01 챌린지는 인증 없이 통과시켜야 한다.
# 이 경로에는 임시 토큰 파일만 놓이므로 노출 위험이 없다.
location ^~ /.well-known/acme-challenge/ {
    auth_basic off;
    root /var/www/html;
}
EOF
```

그리고 80을 듣는 서버 블록(`default`)에 이 스니펫을 포함시킨다:

```bash
sudo sed -i '/auth_basic_user_file \/etc\/nginx\/.htpasswd;/a\    include snippets/acme.conf;' /etc/nginx/sites-available/default
sudo nginx -t && sudo systemctl reload nginx
```

검증 — 401이 아니라 404가 나와야 통과다:

```bash
sudo mkdir -p /var/www/html/.well-known/acme-challenge
echo ok | sudo tee /var/www/html/.well-known/acme-challenge/test > /dev/null
curl -s -o /dev/null -w "%{http_code}\n" http://43.202.142.135/.well-known/acme-challenge/test
```

**200이 나와야 정상.** 401이면 아직 막힌 것이니 다음으로 넘어가지 말 것.

---

## 단계 3. certbot 설치 + 인증서 발급

Ubuntu 22.04는 snap 방식이 공식 권장이다 (apt 버전은 오래됨).

```bash
sudo snap install core && sudo snap refresh core
sudo snap install --classic certbot
sudo ln -sf /snap/bin/certbot /usr/bin/certbot
```

발급 — `--nginx` 대신 `certonly --webroot` 를 쓴다. nginx 설정을 certbot이 멋대로
고치지 않게 하려는 것(우리 설정이 포트별로 복잡해서 자동 편집이 깨질 수 있다):

```bash
sudo certbot certonly --webroot -w /var/www/html \
  -d 내이름-quiz.duckdns.org \
  -d 내이름-eat.duckdns.org \
  -d 내이름-focus.duckdns.org \
  --email 내메일@example.com --agree-tos --no-eff-email
```

성공하면 `/etc/letsencrypt/live/내이름-quiz.duckdns.org/` 에 인증서가 생긴다.

> 실패하면 대부분 단계 2를 안 했거나 DNS 전파 전이다. `--dry-run` 을 붙여 먼저 시험해도 좋다.

---

## 단계 4. nginx를 443 + server_name 기반으로 재작성

`내이름` 부분을 전부 실제 값으로 바꾼 뒤 실행한다.

```bash
sudo tee /etc/nginx/sites-available/https > /dev/null << 'EOF'
# ─── 공통 TLS 설정 ───────────────────────────────────
# 인증서 경로는 3개 도메인 SAN 1장이라 quiz 것 하나만 쓰면 된다.

# 임용 퀴즈
server {
    listen 443 ssl;
    server_name 내이름-quiz.duckdns.org;

    ssl_certificate     /etc/letsencrypt/live/내이름-quiz.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/내이름-quiz.duckdns.org/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 50m;
    auth_basic           $quiz_auth;          # 신뢰 기기 쿠키 있으면 off
    auth_basic_user_file /etc/nginx/.htpasswd;

    root /var/www/quiz;
    index index.html;

    location = /trust {
        auth_basic           "Restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;
        add_header Set-Cookie "quizauth=__TOKEN__; Path=/; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax";
        return 302 /;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8011/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300s;
    }

    location / { try_files $uri $uri.html $uri/ /index.html; }
}

# eatNwrite + 자기관리 기록
server {
    listen 443 ssl;
    server_name 내이름-eat.duckdns.org;

    ssl_certificate     /etc/letsencrypt/live/내이름-quiz.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/내이름-quiz.duckdns.org/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    auth_basic           "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;

    # iOS 단축어용 — 앱 자체 x-api-key로 보호되므로 인증 예외
    location /api/log { auth_basic off; proxy_pass http://127.0.0.1:3012; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }
    location /api/sms { auth_basic off; proxy_pass http://127.0.0.1:3012; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }

    location / { proxy_pass http://127.0.0.1:3012; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }
}

# focus-app (뽀모도로)
server {
    listen 443 ssl;
    server_name 내이름-focus.duckdns.org;

    ssl_certificate     /etc/letsencrypt/live/내이름-quiz.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/내이름-quiz.duckdns.org/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    auth_basic           "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / { proxy_pass http://127.0.0.1:4000; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }
}
EOF

sudo ln -sf /etc/nginx/sites-available/https /etc/nginx/sites-enabled/https
sudo nginx -t && sudo systemctl reload nginx
```

> `__TOKEN__` 은 신뢰 기기 쿠키를 이미 설정한 경우 그 토큰 값으로 바꾼다.
> 아직 안 했으면 `/trust` 블록과 `auth_basic $quiz_auth;` 를 지우고
> `auth_basic "Restricted";` 로 두면 된다. HTTPS에서는 `Secure` 플래그를 붙일 수 있어
> 쿠키 방식이 비로소 안전해진다.

### 80 → 443 리다이렉트

기존 80(default, focus-app)을 리다이렉트로 바꾼다. ACME 경로만 예외로 남긴다:

```bash
sudo tee /etc/nginx/sites-available/default > /dev/null << 'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    location ^~ /.well-known/acme-challenge/ {
        auth_basic off;
        root /var/www/html;
    }

    location / { return 301 https://$host$request_uri; }
}
EOF
sudo nginx -t && sudo systemctl reload nginx
```

---

## 단계 5. 검증

로컬 PC에서:

```bash
curl -sI https://내이름-quiz.duckdns.org | head -3
```

`HTTP/1.1 401` (Basic Auth 프롬프트) 또는 `200` 이 나오고, 인증서 경고가 없으면 성공.

브라우저로 세 주소를 각각 열어 자물쇠 아이콘을 확인한다.

---

## 단계 6. 자동 갱신 확인

certbot snap은 systemd 타이머를 자동 등록한다. 확인:

```bash
systemctl list-timers | grep certbot
sudo certbot renew --dry-run
```

`--dry-run` 이 성공하면 90일마다 자동 갱신된다.

**단, 갱신도 HTTP-01을 쓰므로 단계 2의 ACME 예외가 계속 살아 있어야 한다.**
80 리다이렉트 설정에 해당 location을 남겨둔 이유가 이것이다.

### DuckDNS IP 자동 동기화 (선택)

고정 IP를 붙였다면 불필요하다. 안 붙였다면 IP 변동에 대비해:

```bash
mkdir -p ~/duckdns
cat > ~/duckdns/duck.sh << 'EOF'
#!/bin/bash
echo url="https://www.duckdns.org/update?domains=내이름-quiz,내이름-eat,내이름-focus&token=내토큰&ip=" | curl -k -o ~/duckdns/duck.log -K -
EOF
chmod 700 ~/duckdns/duck.sh
( crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1" ) | crontab -
```

---

## 전환 후 잊지 말 것 (체크리스트)

- [ ] **iOS 단축어 주소 변경** — 자기관리 기록/SMS 단축어가 `http://43.202.142.135:3001/api/log` 를 호출한다. `https://내이름-eat.duckdns.org/api/log` 로 수정.
- [ ] **북마크/홈 화면 아이콘** 전부 새 주소로 교체
- [ ] **신뢰 기기 쿠키 재등록** — 도메인이 바뀌면 쿠키도 새로 심어야 한다. 기기마다 `https://내이름-quiz.duckdns.org/trust` 한 번씩 방문
- [ ] **CLAUDE.md 갱신** — 배포 절차의 접속 주소를 새 도메인으로
- [ ] 프론트 **재빌드는 불필요** — `NEXT_PUBLIC_API_URL=/api` 상대경로라 주소가 바뀌어도 그대로 동작한다 (확인함)
- [ ] 구 포트(8001/3001/3000)를 언제 닫을지 결정. 당분간 열어두고 이관을 확인한 뒤 Lightsail 방화벽에서 제거하는 편이 안전하다.

## 롤백

443 설정만 떼어내면 즉시 원상복구된다:

```bash
sudo rm /etc/nginx/sites-enabled/https
sudo cp /etc/nginx/sites-available/default.bak /etc/nginx/sites-available/default   # 백업해 뒀다면
sudo nginx -t && sudo systemctl reload nginx
```

인증서 자체는 남아 있어도 무해하다.
