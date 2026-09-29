---
name: static-site-cache-stamp
description: 给静态站点（HTML + CSS/JS/图标）自动打内容指纹缓存版本戳，解决"改了样式或脚本、老访客还在吃缓存旧版"的问题。发布时自动重算、无需手动递增版本号。含通用脚本 scripts/cache_stamp.py（自动发现页面引用的本地资源、算合并内容指纹、幂等改写 HTML）、发布后线上一致性核查方法（带版本号 url 必须 200 且 md5 与源文件逐字节一致）。触发场景：静态站点发布/上线、CSS 或 JS 改动后担心用户浏览器缓存、要加 ?v= 版本参数、favicon 不更新、CDN 或 nginx 缓存导致旧版页面。
---

# 静态站点 · 内容指纹缓存版本戳

## 要解决的问题

静态站点直接引用 `style.css` / `app.js` / `favicon.svg` 时，浏览器按 **URL** 缓存。
一旦改完这些文件重新发布，**老访客的 URL 没变，浏览器就继续用本地缓存**，
表现为"我明明改了，用户那边还是旧的" —— 只能让对方强刷（Ctrl+F5），不可接受。

最小成本解法：给引用加查询串 `?v=<版本号>`，让 URL 随内容变化而变化。

## 关键决策：内容指纹 > 手写序号

| 方案 | 问题 |
|---|---|
| 手写 `?v=1`、`?v=2` … 每次发布手动 +1 | 靠人记。忘了就出事故，且**内容没变也翻版本号**，白白让全网重新下载 |
| 全局版本号（每次发布会递增的时间戳/序号） | 改一个 CSS 就让所有 JS 也失效重下，颗粒度太粗 |
| **内容指纹**（推荐） | 内容没变 → 版本号不变（缓存继续有效）；内容一变 → 版本号自动变。**零人工纪律** |

版本号长这样：`20260915-1add915`（日期 + 资源合并 md5 前 7 位）。
日期前缀只是便于人类排查"线上跑的是哪天发的那版"，真正起作用的是后面的指纹。

## 用法

```bash
# 先看会改成什么样（不写盘）
python scripts/cache_stamp.py <站点目录> --dry-run

# 正式打戳
python scripts/cache_stamp.py <站点目录>

# 强制指定版本号
python scripts/cache_stamp.py <站点目录> --version 20260915-hotfix1
```

脚本行为：
- 自动发现站点里所有 `.html` 页面，从 `href` / `src` 里提取**本地**资源引用
  （`.css` / `.js` / `.mjs`，以及 `<link rel="icon|apple-touch-icon">` 的 `.svg` / `.ico`）；
  外链（含 `http(s)://`、`//`、`data:`）一律跳过。
- 对发现的资源文件内容求合并 md5 → 版本号。
- 幂等正则改写：`href="style.css"` 与 `style.css?v=old` 都会被统一成当前版本，可反复执行。
- 读写都用 `newline=''`，**不破坏文件原有行尾（CRLF/LF）与 BOM**。

## 接入发布流程（重要）

别把它当成"发布前要记得手动跑一下"的步骤 —— **让部署脚本自己调**，
否则迟早会漏。在部署脚本打包前插入一次调用即可：

```python
import cache_stamp
version = cache_stamp.stamp(SITE_DIR)   # 版本号自动重算
```

并在发布后的核查里加两条断言：

```bash
# 1) 线上 HTML 里确实带上了版本号
curl -s https://example.com/ | grep -o 'style\.css?v=[^"]*'
# 2) 带版本号的 url 必须 200，且与服务器上的原文件 md5 一致
curl -s "https://example.com/style.css?v=<ver>" | md5sum
md5sum /var/www/site/style.css
```

两个 md5 必须**逐字节相同** —— 这一步能同时抓出「nginx 没生效」「CDN 缓存了旧版」
「上传中断导致文件损坏」三类问题，比只看状态码可靠。

## 踩坑与边界

- **别给所有资源都套全局版本号，尤其是图片。** 图片体积大，如果跟着全局版本号走，
  改一次 CSS 就会让全部图片重新下载，把流量和首屏时间吃光。
  图片要打戳就得按**单文件**指纹；或者更省事：让 nginx 对图片只发 `Cache-Control: no-cache`
  走 ETag / If-Modified-Since 复验，命中就是 304，几乎不花流量，同名换图也能立刻生效。
- **检查脚本自身是否依赖脚本路径。** 加查询串后 URL 变了，若代码里有
  `document.currentScript.src`、`import.meta.url`、相对路径 `fetch()` 这类逻辑，可能被影响；
  发布前 grep 一遍确认没有。
- **`favicon` 要单独记得**：浏览器对 favicon 的缓存极其顽固，而且还有独立于普通 HTTP 缓存的
  favicon 库。给它打戳是成本最低的一招。同理 `<link rel="apple-touch-icon">` 也一起打。
- **`?v=` 与 `#hash` 的顺序**：查询串必须在 `#` 之前，否则会被当成 fragment。
- 版本号变一次 = 全网该资源重新下载一次。所以**别在短时间里反复发**，
  本地预览确认好了再发；本地预览同样吃这个版本号，无副作用。
- 纯静态托管（GitHub Pages / OSS / CDN）也适用，但 CDN 侧的刷新仍可能滞后，
  打戳后 CDN 会把新 URL 当作新对象回源，通常比手动刷 CDN 更省事。
