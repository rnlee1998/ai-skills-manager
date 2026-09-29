#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""给静态站点打「内容指纹」缓存版本戳。

把 HTML 里对本地 CSS / JS / 图标的引用改写成带版本查询串的形式：

    <link rel="stylesheet" href="style.css">      ->  style.css?v=20260915-1add915
    <script src="app.js?v=old"></script>          ->  app.js?v=20260915-1add915

版本号 = 当天日期 + 所有被引用资源内容合并 md5 的前 7 位。
内容没变 -> 版本号不变（老访客继续吃缓存）；内容一变 -> 版本号自动翻新。
因此**不需要靠人记得手动递增**，把 stamp() 挂进部署脚本即可。

CLI:
    python cache_stamp.py <站点目录> [--dry-run] [--version X]

作为库使用:
    import cache_stamp
    ver = cache_stamp.stamp(r'C:\\path\\to\\site')
"""
import os
import re
import sys
import glob
import hashlib
import datetime
import argparse

# 参与打戳的资源类型
CODE_EXT = ('.css', '.js', '.mjs')
# 只有 rel 是 icon 类才打戳的图片资源（favicon 缓存极顽固，值得单独打）
ICON_EXT = ('.svg', '.ico', '.png')

ATTR = re.compile(r'\b(href|src)\s*=\s*"([^"]+)"', re.I)
ICON_REL = re.compile(r'\brel\s*=\s*"[^"]*\b(?:icon|apple-touch-icon)\b[^"]*"', re.I)
SKIP_DIRS = {'.git', 'node_modules', '.workbuddy', '.codebuddy', '__pycache__', 'dist', 'build'}


def _is_local(url):
    u = url.strip()
    if not u or u[0] == '#' or u.startswith('//'):
        return False
    for scheme in ('data:', 'mailto:', 'tel:', 'javascript:', 'blob:'):
        if u.lower().startswith(scheme):
            return False
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.\-]*:', u):   # 任意 scheme: -> 外链
        return False
    return True


def _strip_query(url):
    return url.split('#', 1)[0].split('?', 1)[0].strip()


def _iter_pages(site_dir):
    out = []
    for root, dirs, files in os.walk(site_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            if f.lower().endswith(('.html', '.htm')):
                out.append(os.path.relpath(os.path.join(root, f), site_dir).replace('\\', '/'))
    return sorted(out)


def _discover(html):
    """从一段 HTML 里提取需要打戳的本地资源路径（按出现顺序、去重）。"""
    found = []
    for chunk in html.split('<')[1:]:
        tag = chunk.split('>', 1)[0]
        for m in ATTR.finditer(tag):
            url = m.group(2)
            if not _is_local(url):
                continue
            path = _strip_query(url)
            ext = os.path.splitext(path)[1].lower()
            if ext in CODE_EXT or (ext in ICON_EXT and ICON_REL.search(tag)):
                found.append(path)
    seen, uniq = set(), []
    for p in found:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def content_version(site_dir, pages=None, assets=None):
    """按资源内容算版本号（资源名排序后合并 md5，保证可复现）。"""
    pages = pages or _iter_pages(site_dir)
    names = list(assets) if assets else []
    if not names:
        for page in pages:
            p = os.path.join(site_dir, page)
            with open(p, encoding='utf-8', errors='replace', newline='') as f:
                names += _discover(f.read())
    h = hashlib.md5()
    used = []
    for name in sorted(set(names)):
        ap = os.path.join(site_dir, name.replace('/', os.sep))
        if not os.path.isfile(ap):
            continue
        with open(ap, 'rb') as f:
            h.update(f.read())
        used.append(name)
    stamp = datetime.date.today().strftime('%Y%m%d')
    return '%s-%s' % (stamp, h.hexdigest()[:7]), used


def stamp(site_dir, version=None, dry_run=False, verbose=True):
    """就地改写 HTML 里的资源引用。返回本次使用的版本号。"""
    site_dir = os.path.abspath(site_dir)
    pages = _iter_pages(site_dir)
    if not pages:
        raise SystemExit('no html page found in %s' % site_dir)

    auto, assets = content_version(site_dir, pages)
    ver = version or auto

    targets = sorted(set(assets))
    pats = [(t, re.compile(r'\b(href|src)\s*=\s*"(?P<u>' + re.escape(t) + r')(?:\?[^"]*)?"', re.I))
            for t in targets]

    changed, total = [], 0
    for page in pages:
        p = os.path.join(site_dir, page.replace('/', os.sep))
        # newline='' -> 读写都不翻译行尾，不破坏 CRLF / BOM
        with open(p, encoding='utf-8', newline='') as f:
            src = f.read()
        out, hits = src, 0
        for target, pat in pats:
            out, k = pat.subn(lambda m, t=target: '%s="%s?v=%s"' % (m.group(1), t, ver), out)
            hits += k
        total += hits
        if out != src:
            if not dry_run:
                with open(p, 'w', encoding='utf-8', newline='') as f:
                    f.write(out)
            changed.append('%s(%d)' % (page, hits))

    if verbose:
        print('site    = %s' % site_dir)
        print('pages   = %d  %s' % (len(pages), ', '.join(pages[:6]) + (' ...' if len(pages) > 6 else '')))
        print('assets  = %d  %s' % (len(targets), ', '.join(targets)))
        print('version = %s%s' % (ver, '' if version else '   (auto from content)'))
        print('refs    = %d' % total)
        print('%s  = %s' % ('would write' if dry_run else 'wrote',
                            ', '.join(changed) if changed else '无改动（已是该版本）'))
    return ver


def main(argv=None):
    ap = argparse.ArgumentParser(description='给静态站点打内容指纹缓存版本戳')
    ap.add_argument('site_dir', help='站点根目录（含 index.html 的那一层）')
    ap.add_argument('--dry-run', action='store_true', help='只显示会改成什么，不写盘')
    ap.add_argument('--version', help='强制指定版本号（默认按内容指纹自动生成）')
    a = ap.parse_args(argv)
    stamp(a.site_dir, version=a.version, dry_run=a.dry_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
