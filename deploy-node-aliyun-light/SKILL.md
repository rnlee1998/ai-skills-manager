---
name: deploy-node-aliyun-light
description: 从 Windows 本地把零依赖 Node 服务部署到阿里云国际站轻量应用服务器（Ubuntu 24.04+）的完整流程。包含 SSH 工具准备（paramiko）、公网 NAT 架构适配、systemd 单元配置、iptables 80→8080 端口转发（因安全组默认仅放行 80/443/22）、netfilter-persistent 持久化、smoke-test 限流清理等已验证的步骤与踩坑修复。触发场景：用户拿到阿里云轻量/ECS 服务器（公网 IP + root 密码）要求部署 Node/PWA 站点，或在 NAT 架构下需要解决 80 端口绑定的安全问题。
---

# Deploy Node to Aliyun Light Server

## 概述

从 Windows 工作站通过 SSH 把零依赖 Node 服务部署到阿里云国际站轻量应用服务器（Simple Application Server）的端到端流程。覆盖：SSH 工具链选型（paramiko，无 sshpass 依赖）、NAT 架构适配（实例只有内网 IP，公网 IP 走云网关）、安全组限制下的端口转发（iptables REDIRECT 80→服务端口）、systemd 单元编写与坑点、netfilter-persistent 持久化、防火墙/限流清理。

## 适用场景

- 用户购买阿里云国际站（IP 段 47.79.x 新加坡、8.215.x 香港等）或类似的轻量应用服务器/ECS，提供公网 IP + root 密码
- 服务是零依赖 Node（无 node_modules）或需要快速验证部署可行性
- 服务器在 NAT 网关后，安全组只放行 80/443/22，自定义端口（如 8080）需转发
- 需要 systemd 自启动 + 重启恢复 + 日志轮转

## 核心步骤

### 1. SSH 工具链（Windows 无 sshpass）

Git Bash 自带 `ssh`/`scp` 但**无 sshpass**，密码认证需要交互式。推荐 Python `paramiko`：

```bash
# 在托管 Python venv 安装
"C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe" -m venv "C:/Users/Administrator/.workbuddy/binaries/python/envs/default"
"C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/pip.exe" install paramiko
```

使用 `scripts/ssh-run.py`（已提供）。**认证优先级：`SSH_PASS` 非空则密码登录，否则用 `SSH_KEY` 私钥登录**。阿里云控制台"绑定密钥对"后 sshd 会变成纯 publickey，**密码立刻失效**，此时必须走私钥。

```bash
# 方式 A：私钥登录（推荐，sshd 常为纯 publickey）
export SSH_HOST=1.2.3.4 SSH_USER=root
export SSH_KEY='C:/Users/Administrator/Desktop/workbuddy2.pem'
python scripts/ssh-run.py exec "node -v && free -h"

# 方式 B：密码登录（未绑定密钥对时）
export SSH_HOST=1.2.3.4 SSH_PASS='YourP@ssw0rd' SSH_USER=root
python scripts/ssh-run.py exec "node -v && free -h"

# 上传文件（用 Windows 路径，不要用 Git Bash 的 /tmp/ 映射）
python scripts/ssh-run.py put "C:/path/to/file" /root/file

# 上传整个目录
python scripts/ssh-run.py putdir "C:/local/dir" /remote/dir
```

**用户可能有多把同名 pem**：`Downloads/` 里常出现 `workbuddy.pem`、`workbuddy (1).pem`、`workbuddy2.pem`… 且**内容不同**（对应不同密钥对）。务必用 `ssh-keygen -y -f <pem>` 提取公钥，与用户给的公钥字符串比对确认，别靠文件名猜。新版 `ssh-run.py` 内置候选列表会依次尝试，并在 stderr 打印实际命中的 key 路径。

**重大坑：`pick_key()` 返回的是第一个"能解析"的私钥，不是第一个"能认证"的**。多把 pem 都能被 paramiko 成功 load，但只有一把能登录，按 `CANDIDATE_KEYS` 顺序盲取必然踩 `AuthenticationException`。**必须批量实测**：

```python
# 对全部候选 key 逐个真实 connect，挑能登录的那把（Windows 下跑）
import paramiko, os
HOST = '1.2.3.4'
cands = [('name', r'C:/Users/Administrator/Downloads/workbuddy.pem'), ...]  # 含 .ssh/ 下所有私钥
loaders = [getattr(paramiko, n) for n in ('RSAKey','Ed25519Key','ECDSAKey') if hasattr(paramiko, n)]
for name, path in cands:
    if not os.path.isfile(path):
        print(name, '-> MISSING'); continue
    key = None
    for L in loaders:
        try:
            key = L.from_private_key_file(path); break
        except Exception: pass
    if key is None:
        print(name, '-> UNPARSEABLE'); continue
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        c.connect(HOST, port=22, username='root', pkey=key, timeout=15,
                  allow_agent=False, look_for_keys=False)
        print(f'{name} -> SUCCESS'); c.close()
    except Exception as e:
        print(f'{name} -> FAIL: {type(e).__name__}')
```

实测记录：本机 `Downloads/workbuddy.pem`（RSA）可用；`workbuddy2.pem` 系与 `.ssh/aliyun_deploy`（ed25519）均认证失败——**ed25519 是最新生成的，不等于已绑定到服务器**，新生成的 key 必须在阿里云控制台"绑定密钥对"并重启实例后才生效。

**先探测服务器允许的认证方式**（避免对纯 publickey 机器白试密码）：

```python
t = paramiko.Transport(('1.2.3.4', 22)); t.connect(); t.auth_none('root')
# 抛 BadAuthenticationType，异常信息里 allowed types 即为可用方式，如 ['publickey']
```

**paramiko 版本差异**：部分版本没有 `DSSKey`，写死 `(RSAKey, Ed25519Key, ECDSAKey, DSSKey)` 会抛 `AttributeError`。用 `getattr(paramiko, n)` + `hasattr` 过滤后再遍历。

### 2. 探测服务器环境

```bash
python scripts/ssh-run.py exec "
echo '=== OS ==='; cat /etc/os-release | head -3
echo '=== NODE ==='; node -v 2>/dev/null || echo 'NOT installed'
echo '=== PORTS ==='; ss -tlnp | grep -E ':80 |:443|:8080'
echo '=== NET ==='; ip addr show | grep 'inet ' | grep -v 127.0.0.1
echo '=== MEM/DISK ==='; free -h | head -2; df -h / | tail -1
"
```

**关键发现**：阿里云轻量服务器的 eth0 通常只有内网 IP（如 172.21.55.92/18），公网 IP 走云网关 NAT 映射。**安全组默认仅放行 80/443/22**，其他端口（8080 等）会被网关 502 "upstream connect failed" 拦截。

### 3. 本地打包 + 上传

```bash
# 本地打包（排除 node_modules/，包含 server.js、public/、data/、config.json、deploy/）
cd your-project
tar czf /tmp/deploy.tar.gz server.js package.json config.json Dockerfile README.md .gitignore deploy public tools data

# 上传 + 解压
cygpath -w /tmp/deploy.tar.gz  # Git Bash → Windows 路径
python scripts/ssh-run.py put "C:/Users/.../Temp/deploy.tar.gz" /root/deploy.tar.gz
python scripts/ssh-run.py exec "mkdir -p /opt/app && cd /opt/app && tar xzf /root/deploy.tar.gz"
```

### 4. 安装 Node（如缺失）

```bash
python scripts/ssh-run.py exec "
if ! command -v node >/dev/null 2>&1 || [ \$(node -v | cut -d. -f1 | tr -d v) -lt 16 ]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
node -v
"
```

### 5. systemd 服务单元（踩坑：heredoc 引号坑）

**坑 1**：heredoc 用 `<<'EOF'`（带引号）→ `$(command -v node)` **不展开** → ExecStart 变成字面无效命令 → 状态 `203/EXEC`。

**解决**：直接写死 `/usr/bin/node` 绝对路径，或用 `<<EOF`（不带引号）让 $() 展开。

```ini
# /etc/systemd/system/your-app.service
[Unit]
Description=Your App
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/app
ExecStart=/usr/bin/node /opt/app/server.js   # ← 必须绝对路径
Restart=always
RestartSec=2
StandardOutput=append:/var/log/your-app.log
StandardError=append:/var/log/your-app.log

# 资源上限（轻量 1G 内存机，700M 留余量）
MemoryMax=700M
TasksMax=4096

# 安全加固
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/app/data

[Install]
WantedBy=multi-user.target
```

**坑 2**：node 监听 1024 以下端口（80/443）需要 root 或 file capability。但 `NoNewPrivileges=true` 与 `setcap cap_net_bind_service=+ep` **不兼容**——systemd 服务用 file cap 绑低端口会失败。

**最优解**：保持服务监听 8080（无特权），用 iptables 把 80 转发到 8080（见步骤 6）。

启用 + 启动：

```bash
python scripts/ssh-run.py exec "
id -u www-data >/dev/null || useradd -r -s /usr/sbin/nologin www-data
chown -R www-data:www-data /opt/app/data
chmod 700 /opt/app/data
systemctl daemon-reload
systemctl enable your-app
systemctl restart your-app
systemctl is-active your-app
"
```

### 6. iptables 端口转发 + 持久化（NAT 架构关键）

公网 IP 47.79.x 走云网关，安全组只放行 80。把请求转发到实例的 8080：

```bash
python scripts/ssh-run.py exec "
# 转发 80 → 8080（PREROUTING 链对进入 eth0 的流量生效）
iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 8080

# 持久化（重启后自动加载）
apt-get install -y iptables-persistent
netfilter-persistent save

# 验证持久化
grep REDIRECT /etc/iptables/rules.v4
"
```

**坑**：REDIRECT 对 `127.0.0.1` **不生效**（loopback 流量走 INPUT 不经 PREROUTING），本机 `curl 127.0.0.1:80` 永远测不到。必须从**公网**或 `eth0` 内网 IP 验证。

### 7. 公网验证

```bash
# 本机（绕过 /tmp 路径问题用 Windows 路径或环境变量）
curl -s -o /dev/null -w 'HTTP:%{http_code} time:%{time_total}s\n' http://SERVER_IP/
curl -s http://SERVER_IP/api/health
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://SERVER_IP/app.js
```

### 8. smoke-test 限流清理

rateLimit 是**内存态按 IP 累计**（`reportPerHour:15` 等）。smoke-test 用 X-Real-IP 模拟不同用户跑完后，**第二次跑立即 429**。

**解决**：每次跑 smoke-test 前 `systemctl restart your-app` 清零内存：

```bash
python scripts/ssh-run.py exec "
systemctl restart your-app
sleep 2
cd /opt/app && node tools/smoke-test.js http://127.0.0.1:8080 2>&1 | tail -8
"
```

**注意**：smoke-test 用 `X-Real-IP` 头（不是 `X-Forwarded-For`），server.js 的 `getClientIp()` 需在 `trustProxy:true` 下优先信任 X-Real-IP 才能正确模拟不同用户。

### 9. agent-browser 验证的局限

Windows headless Chromium 的 daemon **经常连不上公网 IP**（显示 `chrome-error://chromewebdata/`），但服务器本身正常。这是 daemon 网络沙箱问题，不是部署问题。

**验证策略**：
- 用 `curl` 验公网接口、API、静态资源
- agent-browser 只用于本地 `127.0.0.1` 验证（视觉/交互）
- 真实视觉验证：用户在真实浏览器打开公网 IP 人工确认

## 场景 B：部署纯静态站点（HTML/CSS/JS，无后端）

当交付物是自包含 HTML（如数据看板、报告页）时，**不需要 systemd、不需要建用户、不需要 Node**。但如果 80 端口已被既有 Node 应用占用（经 iptables REDIRECT 转发），正确做法是**装 nginx 接管 80，再反代旧应用**，而不是换端口——安全组只放行 80/443/22，8081 之类公网根本不通。

目标架构（双站共存，旧应用零改动）：

```
公网 :80 → nginx
  /gold/  → alias /var/www/gold/    # 新静态站
  /       → proxy_pass 127.0.0.1:8080  # 旧 Node 应用
```

步骤：

```bash
# 1) 装 nginx
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq nginx

# 2) 上传静态目录（中文文件名先在本地 cp 成 ASCII 名，避免 URL 转义/传输坑）
python scripts/ssh-run.py putdir "C:/local/gold" /var/www/gold

# 3) 写站点配置 → /etc/nginx/sites-available/<name>，然后：
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/<name> /etc/nginx/sites-enabled/<name>
```

站点配置模板：

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    charset utf-8;

    gzip on;
    gzip_types text/html text/css application/javascript application/json;
    gzip_min_length 1024;

    location = /gold { return 301 /gold/; }        # 无尾斜杠补正

    location /gold/ {
        alias /var/www/gold/;
        index index.html;
        autoindex on;                               # 可选：列出全部归档
        add_header Cache-Control "no-cache, must-revalidate";
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 60s;
    }
}
```

**切换 80 端口归属必须按此顺序，否则会短暂断流**：

```bash
# ① 先启 nginx 绑定 80（此时 iptables REDIRECT 仍生效，流量照旧走旧应用，服务不中断）
systemctl enable nginx && systemctl restart nginx
# ② 再删转发规则，流量才切给 nginx
iptables -t nat -D PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 8080
netfilter-persistent save     # 持久化，否则重启后规则复活、nginx 抢不到流量
```

注意顺序不能反：先删规则再启 nginx 会出现"规则已删、nginx 未起"的空窗期。

**每日更新的目录用软链接做"最新"入口**，避免每天改文件内容或改 nginx 配置：

```bash
ln -sf gold_20260831.html /var/www/gold/latest.html   # 自动化每天只需重链一次
```

**验证**：公网 `curl` 拉到的文件应与本地源文件 **MD5 一致**（`md5sum` 对比），仅看 200 不够（可能命中了错误页面或缓存）。注意 Git Bash 下 `curl -o /dev/null` 会报 exit 23 且 size 显示 0B，这是写 /dev/null 的问题，不代表响应为空——要落到真实文件再比对。

## 场景 C：零依赖部署 HTTPS（certbot + sslip.io 反解域名）

> 适合：阿里云轻量有公网 IP 443 可用，零依赖 Node PWA 项目，无正式域名，**需要 Geolocation / Service Worker / nbg.getUserMedia 等只能在安全上下文跑的 API**。下面把整个流程压缩到 8 条命令。

**为什么不用 nip.io**：nip.io 在国内公共 DNS（114 / 阿里 223.5.5.5 / 腾讯 119.29.29.29 / Google 8.8.8.8）**全部解析失败**，用户直接打开就 `ERR_NAME_NOT_RESOLVED`。**改用 sslip.io**（同样把 `47-79-20-187.sslip.io` 反解到 47.79.20.187），114 和阿里 DNS 均能正常解析。

**1. 装 certbot 与 nginx 插件**

```bash
apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq certbot python3-certbot-nginx
```

**2. 备份现有 nginx 配置**（certbot --nginx 会原地修改）

```bash
cp /etc/nginx/sites-available/<你的站点> /etc/nginx/sites-available/<你的站点>.bak.$(date +%s)
```

**3. 申请第一张证书**（HTTP-01 挑战走 80 端口，不需要 443 放行）

```bash
certbot --nginx -d 47-79-20-187.sslip.io \
  --non-interactive --agree-tos --register-unsafely-without-email --redirect --keep-until-expiring
```

证书落到 `/etc/letsencrypt/live/47-79-20-187.sslip.io/{fullchain.pem, privkey.pem}`，有效期 90 天。

**4. 一张证书同时覆盖双域名**（给 nip.io 也签上，国外用户/调试用得到）

```bash
certbot --nginx --cert-name 47-79-20-187.sslip.io \
  -d 47-79-20-187.sslip.io -d 47-79-20-187.nip.io \
  --expand --non-interactive --agree-tos --register-unsafely-without-email --redirect --keep-until-expiring
```

certbot 会自动：① 改 80 server 加 301→HTTPS；② 新增 443 server，SSL/TLS 路径写进 `listen 443 ssl` + `ssl_certificate`；③ `include /etc/letsencrypt/options-ssl-nginx.conf` + `ssl_dhparam`。

**5. reload 并服务器本地验证**（必做，别只看公网）

```bash
systemctl reload nginx
ss -lntp | grep ':443 '                            # 应有 nginx worker
curl -s -o /dev/null -w '%{http_code}\n' --resolve '47-79-20-187.sslip.io:443:127.0.0.1' https://47-79-20-187.sslip.io/
echo | openssl s_client -connect 127.0.0.1:443 -servername 47-79-20-187.sslip.io 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

`reload` 不会重启 worker，配置热加载。

**6. 公网真实链路验证**（关键：服务器自己走公网 DNS + 公网 IP 出去再回来，是最稳的"外部视角"）

```bash
curl -s -o /dev/null -w 'https sslip => %{http_code} ssl=%{ssl_verify_result}\n' --max-time 15 https://47-79-20-187.sslip.io/
curl -s -o /dev/null -w 'http  sslip => %{http_code} -> %{redirect_url}\n' --max-time 15 http://47-79-20-187.sslip.io/
curl -s -o /dev/null -w 'https /gold/  => %{http_code}\n' --max-time 15 https://47-79-20-187.sslip.io/<其它项目路径>
```

`ssl_verify_result=0` 才是真通过；exit 35 = TLS 握手失败（多半是本地代理或 DNS 拦截）。

**7. 让浏览器真的能定位**（HTTPS 的核心收益）

加一段页面侧提示条：HTTP 访问时浏览器**直接屏蔽** `navigator.geolocation`，点了按钮不会有任何反应。提示条检测 `window.isSecureContext`：

```js
function initSecureTip() {
  var tip = document.querySelector('#httpsTip');
  if (!tip) return;
  var host = location.hostname;
  var isLocal = host === 'localhost' || host === '127.0.0.1' || host === '::1';
  if (window.isSecureContext || isLocal) return;
  tip.hidden = false;
  document.body.classList.add('has-https-tip');
  // JS 测量提示条实际高度后写入 --tip-h，让 CSS 决定页面下推距离
  document.documentElement.style.setProperty('--tip-h', tip.offsetHeight + 'px');
  document.querySelector('#httpsGo').addEventListener('click', function () {
    var target = /^\d+\.\d+\.\d+\.\d+$/.test(host)
      ? 'https://' + host.replace(/\./g, '-') + '.sslip.io'  // IP 自动反解到 sslip.io
      : 'https://' + location.host;
    location.href = target + location.pathname + location.search + location.hash;
  });
}
```

**不要在 nginx 层强制 IP HTTP 跳 HTTPS**——`sslip.io` 是个公共服务，万一挂了 IP 访问就彻底打不开。提示条方案更稳。

**8. 端到端 puppeteer 验证**（把"应该能用"变成"实测能用"）

```js
// 设模拟坐标 → 打开 HTTPS 页面 → 允许 geolocation 权限 → 点定位 → 检查地图中心
await page.setGeolocation({ latitude: 25.0415, longitude: 102.7185 });
await ctx.overridePermissions(new URL(TARGET).origin, ['geolocation']);
await page.goto(TARGET, { waitUntil: 'networkidle2' });
await page.click('#btnLocate');
await sleep(3000);
const view = JSON.parse(await page.evaluate(() => localStorage.getItem('kw_view')));
// 验证 view.lat/lng 与 setGeolocation 偏差 < 100m
```

铁证定位能力真实可用的标志：localStorage 里存的视图坐标 = setGeolocation 给的坐标，距离 0 km。

**自动续期**：certbot.timer 默认 enabled，每天 8:22 检查，到期前 30 天自动续。**不要关掉**。

**仍需用户手动处理**：HTTPS 上线后，所有依赖 referrer / Key 白名单的第三方 API（腾讯地图 JS SDK / 腾讯 WebService API / 高德 / Google Maps 等）都要在对应控制台把 `47-79-20-187.sslip.io` 加进域名白名单，否则会降级或返回空数据。程序化做不了这一步。

## 部署后运维速查

```bash
# 服务
systemctl status your-app
systemctl restart your-app
journalctl -u your-app -f

# 防火墙
iptables -t nat -L PREROUTING -n
cat /etc/iptables/rules.v4

# 数据
cat /opt/app/data/reports.jsonl | wc -l
ls -la /opt/app/data/

# 更新代码（本地打包后）
cd /opt/app && tar xzf /path/to/deploy.tar.gz --overwrite-dir
systemctl restart your-app
```

## 通用踩坑清单

1. **阿里云轻量服务器 NAT 架构**：eth0 内网 IP，公网走网关，安全组默认仅 80/443/22
2. **systemd heredoc 引号**：用 `<<'EOF'` 不会展开 `$()`，ExecStart 写绝对路径
3. **NoNewPrivileges + setcap 不兼容**：用 iptables 转发代替 setcap 绑低端口
4. **iptables REDIRECT 对 localhost 无效**：本机 127.0.0.1 测不到，必须用 eth0 IP 或公网
5. **rateLimit 内存态**：smoke-test 第二次跑前必须 restart 服务清零
6. **agent-browser 公网连不上**：daemon 网络沙箱，用 curl + 真实浏览器人工验
7. **Git Bash `/tmp/` 路径**：paramiko（Windows 原生 Python）不识别，用 `cygpath -w` 转 Windows 路径
8. **密码含特殊字符**：单引号包裹避免 shell 解释，验证 `repr(pass)` 完整
9. **PWA/SPA 部署后用户报"修了的 bug 还在"**：80% 是 Service Worker 缓存优先在搞鬼——
   - `sw.js` 自身的 HTTP 缓存头必须 `no-cache, no-store, must-revalidate`（它控制所有缓存，是"总开关"）
   - 静态资源走 `cache-first` 时，HTML 命中缓存返回**旧 HTML** → 旧 HTML 引用 `?v=旧` 资源 → 永远拿不到新版本。**HTML 请求必须走 network-first**（cache 作为离线兜底）
   - 用户当前激活的旧 SW 不会自动让位给新 SW；新 SW `skipWaiting + clients.claim` 后需 `postMessage({type:'sw-updated'})` 通知客户端 `location.reload()` 才能让老用户立即看到修复
   - 真要可靠：**告诉用户硬刷新一次**（Ctrl+Shift+R / 无痕模式），下次部署起自动
10. **puppeteer `evaluate(el.click())` 绕过 hit-testing，制造"假成功"**：
    - JS 派发 click 不走浏览器 hit-testing（元素被遮挡照样能"点"中）
    - 真实用户手指点击 100% 命中遮挡层 → 拿不到事件 → "按钮没反应"
    - **必须用 `page.mouse.click(x, y)`** 走真实命中测试
    - **必须先 `document.elementFromPoint(x, y)` 验证 topEl === target**，否则你测的是"JS 能派发事件"而不是"用户能点中"
    - 完整工作流：每个交互前用 `elementsFromPoint` 拿堆叠链，找出 `z-index:1000` 的隐藏覆盖层
    - 第三方地图 SDK（腾讯/百度/高德）**几乎都有这个问题**：SDK 内部创建 `position:absolute; z-index:1000` 的全屏 div 拦截 pointer 事件
    - 解法：给地图容器加 `isolation: isolate; z-index: 1;` 创建独立 stacking context，把 SDK 内部 1000 层关进笼子；同时把业务 UI 抬到 `z-index: 1200+` 作双保险
9. **sshpass 不可用**：用 paramiko + 环境变量传密码（避免命令行历史）
10. **deploy.sh cp 自复制失败**：SRC_DIR 与 APP_DIR 相同会报 "are the same file"，手动执行 setup_systemd 阶段

## 纯静态站点（HTML 看板）与 nginx 多 server 块

适用场景：只要传一个 `index.html` 就能上线的看板/报表（无 Node、无构建）。

**机器档案（已验证，2026-09-08 更新）**：47.79.20.187（Ubuntu 24.04，nginx 1.24，Certbot 已签 nip.io/sslip.io 证书）
- 可用私钥：`C:\Users\Administrator\Desktop\workbuddy.pem`（RSA，root）。⚠️ pem 会换：08-31 时是 `workbuddy2.pem`，09-08 起换成 `workbuddy.pem`（旧文件被用户删除）。**脚本必须维护多密钥候选列表逐一实测**，不要写死单把；`~/.ssh/aliyun_deploy` 认证失败
- 站点配置：`/etc/nginx/sites-available/gold-dashboard`（`sites-enabled/` 里是软链）
- 静态站点约定目录：`/var/www/<name>/`，`/var/www/html/` 只是空壳
- 当前路由：`/` → `/var/www/home/`（站点索引卡片页）；`/kunming-water/` → 反代 127.0.0.1:8080（昆明供水地图，2026-09-08 从根迁到子目录）；`/gold/`、`/etf-opportunity/`、`/exam/`（应知应会刷题题库，2026-09-09 上线）为静态看板
- **域名 `nexbase.online` 已上线（2026-09-09）**：解析到 47.79.20.187，Let's Encrypt 证书已签（nginx 站点 `/etc/nginx/sites-available/nexbase`，根路径 301 → /exam/）。对外推荐用 `https://nexbase.online/...`，比 sslip.io/nip.io 更正式。
- **exam-server 服务（2026-09-09 上线）**：刷题网页的用户/后台后端，零依赖 Node，监听 `127.0.0.1:8099`（systemd `exam-server.service`，www-data 运行，数据 `/opt/exam-server/data/` 下 JSON 文件）。nginx 反代 `/exam/api/` → `http://127.0.0.1:8099/api/`（剥前缀）。**新增带后端的站点时，反代 location 要同时插进 gold-dashboard（3 个 server 块）和 nexbase（1 个 443 块）**。后台页 `/var/www/exam/admin.html`，管理账号 `admin`（密码见用户处）。运维：`systemctl status/restart exam-server`、日志 `/var/log/exam-server.log`、数据备份直接 cp `/opt/exam-server/data/`。
- **HTTPS 现状（2026-09-09 复核）**：certbot 证书 `47-79-20-187.nip.io` 已同时覆盖 sslip.io + nip.io 两个域名，`certbot.timer` enabled+active 自动续期。sslip.io 下 HTTP 301→HTTPS；**IP 的 http 不跳 HTTPS**（故意保留兜底）。因此新增 location 后 HTTPS 是自动生效的，不需要重新签证书。
- **nip.io 解析**：技能旧记录称 nip.io 在国内 DNS 解析失败，但 2026-09-09 实测本机 DNS 与阿里 223.5.5.5 **均能解析**。结论以实测为准，不要盲信旧记录。
- **首页 `/var/www/home/index.html` 已升级为 HTTPS 入口导航页**（2026-09-09）：每卡片下方带完整 HTTPS 地址 + 一键复制；卡片结构为 `<div class="card">` + 内层 `<a class="cardlink">`（避免 `<button>` 嵌在 `<a>` 里的非法嵌套）。新增服务卡片时沿用此结构。
- 新增静态站的完整脚本见本工作区 `deploy.py`（上传 → 备份到 /root/nginx-backups → 在每个 `location /gold/ {}` 块后幂等插入 → `nginx -t` 失败即回滚 → reload → HTTP/HTTPS 双域名 curl + MD5 校验）；首页索引卡片插入脚本见 `addcard.py`

**坑 A：nginx 配置备份别放 `sites-enabled/`**
`cp conf conf.bak.$ts` 会被 `include /etc/nginx/sites-enabled/*` 一起加载 → `duplicate default server for 0.0.0.0:80` → 整个 nginx 起不来。备份一律放 `/root/nginx-backups/`。

**坑 B：配置里有多组 server 块，只改一处会导致 HTTPS 不生效**
该文件含 3 组带 `location /gold/` 的 server 块（nip.io 与 sslip.io 各自的 80/443）。只在第一组插入新 location 时：HTTP 正常，HTTPS 落到默认 server 的反代（返回完全无关的站点）。
正确做法——**先清后插，保证幂等**：

```python
MARK  = "    # <你的站点注释>"
ALIAS = "alias /var/www/<name>/;"
while ALIAS in conf and MARK in conf:          # 清掉历史插入，防 duplicate location
    j = conf.index(ALIAS); i = conf.rfind(MARK, 0, j)
    k = conf.index("    }\n", j) + len("    }\n")
    while conf[k] == "\n": k += 1
    conf = conf[:i] + conf[k:]
pat = re.compile(r"(    location /gold/ \{\n(?:[^\n]*\n)*?    \}\n)")
conf, n = pat.subn(lambda m: m.group(1) + "\n" + BLOCK, conf)   # n 应为 server 块数
```

**坑 C：`nginx -t` 判定**
配置里本来就有 `duplicate MIME type "text/html"` 的 **warn**（无害）。判定必须看 `test is successful` 且无 `[emerg]`，不能只 grep "successful" 之外的 warn 就回滚。

**流程模板**：`build.py`（解析源数据→自包含 HTML） + `deploy.py`（生成→sftp 上传→改 nginx→`nginx -t`→`systemctl reload nginx`→curl 验证 HTTP 与 HTTPS 两个 URL 的 `<title>`）。验证要同时看 http 和 https，只测一个会漏坑 B。

## 场景 D：把根路径应用整体迁到子目录（根腾出来做索引页）

> 适合：某应用原本独占 `/`（如昆明供水地图反代 8080），现在要把它挪到 `/xxx/`，根路径改成站点索引页。
> 2026-09-08 在 47.79.20.187 上跑通（`/` → `/kunming-water/`）。

**核心思路：前缀在 nginx 层剥离，应用主体零改动。** `proxy_pass http://127.0.0.1:8080/;`（**带尾斜杠**）会把 `/kunming-water/foo` 变成 `/foo` 再转发，Node 应用仍按根路径工作。所以后端路由完全不用动，只需要让**浏览器发出的请求**带上前缀。

**1) nginx：每个 server 块两处改动**

```nginx
location = /kunming-water { return 301 /kunming-water/; }   # 无尾斜杠补正

location /kunming-water/ {
    proxy_pass http://127.0.0.1:8080/;      # 尾斜杠 = 剥离前缀，关键
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
}

# SSE 必须单独关缓冲，否则事件被 nginx 攒着不下发（原本在根路径时同样要这么配）
location /kunming-water/api/stream {
    proxy_pass http://127.0.0.1:8080/api/stream;   # 这条要写全路径，不能只写 /
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding on;
    proxy_read_timeout 3600s;
}

location / {
    root /var/www/home; index index.html; try_files $uri $uri/ =404;
}
```

改法：用 Python 正则找出所有 4 空格缩进、含 `proxy_pass http://127.0.0.1:8080;` 的 `location / { ... }` 块整体替换（本机 3 处，见坑 B），别用 sed 逐行改。

**2) 前端：给所有绝对路径加前缀**（`BASE = '/kunming-water'`）

- `index.html`：`href="/` → `href="/kunming-water/`，`src="/` 同理；同时把资源版本戳 `?v=14` 升到 `?v=15` 破缓存
- 运行时配置里若有 `apiBase` 之类变量（本项目 `public/config.js` 的 `window.KW_CONFIG.apiBase`），设成 `"/kunming-water"`，前端所有 `fetch(API + '/api/...')` 自动带上前缀——**这类集中式 API 基址是迁移能否省事的关键，先 grep 确认**
- `manifest.webmanifest`：`start_url`、`scope` → `/kunming-water/`，图标 `src` 加前缀
- `sw.js`：缓存版本号 +1（v14→v15）；`SHELL` 里各项加前缀；所有 `url.pathname === '/xxx'` 判断改成 `BASE + '/xxx'`
- `app.js`：`navigator.serviceWorker.register('/sw.js')` → `register('/kunming-water/sw.js')`
- 独立页面（如 `admin.html`）若自己内联了 `var API = window.KW_CONFIG... || ''`，兜底值要改成 `'/kunming-water'`，否则它的 API 请求会打到根路径 404

**3) 根路径放一个"自毁" SW 清理老注册**
老用户浏览器里 scope 为 `/` 的 SW 仍然活着。在 `/var/www/home/sw.js` 放一个只做 `caches.delete(非新版本缓存)` + `registration.unregister()` 的 SW，浏览器更新 `/sw.js` 时会把它装上来并自我注销。注意别把新版本缓存（`kw-water-v15`）也删了。

**4) 验证清单**
`/`、`/kunming-water/`、`/kunming-water/api/health`、`/kunming-water/app.js?v=15`、`/kunming-water/admin.html`、其它子站（`/gold/` 等）全 200；无尾斜杠 301；SSE 用 `curl -N --max-time 5` 能收到 `event: hello`；**HTTP 和 HTTPS 两个域名都要测**。

## 配套脚本

- `scripts/ssh-run.py`：基于 paramiko 的 SSH 执行/上传工具（环境变量传密码）
