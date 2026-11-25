#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
極簡靜態網站產生器（不需安裝任何套件，Python 3.8+ 即可）

  python build.py                       產生整個網站
  python build.py new 網址代號 "文章標題"   建立一篇新文章草稿（_posts/日期-代號.html）
  python build.py serve                 產生後在 http://localhost:8000 預覽

文章放在 _posts/ ，每篇最上方是 --- 包起來的資料區，下面是 HTML 內文。
"""
import html
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "site.json").read_text("utf-8"))
OUT = (ROOT / CFG.get("output", "public")).resolve()
TPL = ROOT / "_templates"
POSTS = ROOT / "_posts"
BASE = CFG["base_url"].rstrip("/")
PER_PAGE = int(CFG.get("per_page", 9))
# 輸出到專案根目錄時，只會清掉這些自動產生的路徑
GENERATED = ["index.html", "404.html", "sitemap.xml", "feed.xml", "robots.txt",
             "articles", "category", "page", "about"]


def tpl(name):
    return (TPL / name).read_text("utf-8")


def render(text, ctx):
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(ctx.get(m.group(1), "")), text)


def esc(s):
    return html.escape(str(s), quote=True)


def parse_post(path):
    raw = path.read_text("utf-8").lstrip("﻿")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
    if not m:
        raise SystemExit(f"{path.name}: 缺少 --- 資料區")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    meta["body"] = m.group(2).strip()
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)
    meta.setdefault("slug", stem)
    meta.setdefault("date", path.stem[:10])
    meta.setdefault("category", CFG.get("default_category", "guide"))
    meta["draft"] = meta.get("draft", "false").lower() == "true"
    meta["url"] = f"/articles/{meta['slug']}/"
    return meta


def add_heading_ids(body):
    """替 h2/h3 加上 id，回傳 (新內文, 目錄 HTML)。"""
    toc, n = [], [0]

    def repl(m):
        n[0] += 1
        level, attrs, text = m.group(1), m.group(2), m.group(3)
        hid = f"s{n[0]}"
        toc.append((int(level), hid, re.sub(r"<[^>]+>", "", text)))
        return f'<h{level} id="{hid}"{attrs}>{text}</h{level}>'

    body = re.sub(r"<h([23])((?:\s(?!id=)[^>]*)?)>(.*?)</h\1>", repl, body, flags=re.S)
    if len(toc) < 3:
        return body, ""
    items = "".join(f'<li class="toc-l{lv}"><a href="#{hid}">{esc(t)}</a></li>' for lv, hid, t in toc)
    return body, f'<nav class="toc"><p class="toc-title">{esc(CFG.get("toc_label", "本文目錄"))}</p><ol>{items}</ol></nav>'


def cat_name(key):
    return CFG.get("categories", {}).get(key, key)


def card(p):
    return render(tpl("card.html"), {
        "url": p["url"], "title": esc(p["title"]), "description": esc(p.get("description", "")),
        "date": p["date"], "image": p.get("image", ""), "image_alt": esc(p.get("image_alt", p["title"])),
        "category": esc(cat_name(p["category"])), "category_url": f"/category/{p['category']}/",
    })


def nav_html():
    links = [("/", CFG.get("home_label", "首頁"))]
    links += [(f"/category/{k}/", v) for k, v in CFG.get("categories", {}).items()]
    links.append(("/about/", CFG.get("about_label", "關於本站")))
    return "".join(f'<a href="{u}">{esc(t)}</a>' for u, t in links)


def page(content, title, description, path, image="", head_extra=""):
    full_title = title if title == CFG["site_name"] else f"{title}｜{CFG['site_name']}"
    og = f'{BASE}{image}' if image.startswith("/") else (image or "")
    return render(tpl("base.html"), {
        "content": content, "title": esc(full_title), "description": esc(description),
        "canonical": f"{BASE}{path}", "site_name": esc(CFG["site_name"]),
        "tagline": esc(CFG.get("tagline", "")), "nav": nav_html(), "year": date.today().year,
        "og_image": og, "lang": CFG.get("lang", "zh-Hant-TW"), "head_extra": head_extra,
        "footer_note": CFG.get("footer_note", ""),
    })


def write(rel, text):
    target = OUT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, "utf-8", newline="\n")


def paginate(posts, prefix, heading, intro):
    pages = [posts[i:i + PER_PAGE] for i in range(0, len(posts), PER_PAGE)] or [[]]
    for i, chunk in enumerate(pages, 1):
        path = prefix if i == 1 else f"{prefix}page/{i}/"
        pager = ""
        if len(pages) > 1:
            prev = f'<a href="{prefix if i == 2 else f"{prefix}page/{i-1}/"}">« 上一頁</a>' if i > 1 else ""
            nxt = f'<a href="{prefix}page/{i+1}/">下一頁 »</a>' if i < len(pages) else ""
            pager = f'<nav class="pager">{prev}<span>{i} / {len(pages)}</span>{nxt}</nav>'
        content = render(tpl("list.html"), {
            "heading": esc(heading), "intro": intro, "cards": "".join(card(p) for p in chunk),
            "pager": pager, "count": len(posts),
        })
        write(path.lstrip("/") + "index.html", page(content, heading, CFG.get("description", ""), path))


def build():
    if OUT == ROOT:
        for name in GENERATED:
            t = ROOT / name
            if t.is_dir():
                shutil.rmtree(t)
            elif t.exists():
                t.unlink()
    else:
        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir(parents=True)
        for d in ("assets", "images"):
            if (ROOT / d).exists():
                shutil.copytree(ROOT / d, OUT / d)
        for f in CFG.get("copy_files", []):
            if (ROOT / f).exists():
                shutil.copy2(ROOT / f, OUT / f)

    posts = [parse_post(p) for p in sorted(POSTS.glob("*.html"))]
    posts = [p for p in posts if not p["draft"]]
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)

    # 文章頁
    for i, p in enumerate(posts):
        body, toc = add_heading_ids(p["body"])
        related = [q for q in posts if q is not p][:3]
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        figure = ""
        if p.get("image"):
            figure = (f'<figure class="hero-img"><img src="{p["image"]}" alt="{esc(p.get("image_alt", p["title"]))}" '
                      f'width="800" loading="eager"></figure>')
        ld = json.dumps({
            "@context": "https://schema.org", "@type": "BlogPosting", "headline": p["title"],
            "datePublished": p["date"], "dateModified": p.get("updated", p["date"]),
            "image": f"{BASE}{p['image']}" if p.get("image") else None,
            "author": {"@type": "Organization", "name": CFG["site_name"]},
            "mainEntityOfPage": f"{BASE}{p['url']}", "description": p.get("description", ""),
        }, ensure_ascii=False)
        content = render(tpl("post.html"), {
            "title": esc(p["title"]), "date": p["date"], "category": esc(cat_name(p["category"])),
            "category_url": f"/category/{p['category']}/", "figure": figure, "toc": toc, "body": body,
            "related": "".join(card(q) for q in related),
            "newer": f'<a class="newer" href="{newer["url"]}">« {esc(newer["title"])}</a>' if newer else "",
            "older": f'<a class="older" href="{older["url"]}">{esc(older["title"])} »</a>' if older else "",
            "description": esc(p.get("description", "")), "disclaimer": CFG.get("disclaimer", ""),
        })
        head = f'<meta property="og:type" content="article"><script type="application/ld+json">{ld}</script>'
        write(f"articles/{p['slug']}/index.html",
              page(content, p["title"], p.get("description", ""), p["url"], p.get("image", ""), head))

    # 首頁、分類
    paginate(posts, "/", CFG["site_name"], CFG.get("home_intro", ""))
    for key, name in CFG.get("categories", {}).items():
        paginate([p for p in posts if p["category"] == key], f"/category/{key}/", name, "")

    # 關於、404
    about = render(tpl("simple.html"), {"heading": esc(CFG.get("about_label", "關於本站")),
                                         "body": CFG.get("about_html", "")})
    write("about/index.html", page(about, CFG.get("about_label", "關於本站"), CFG.get("description", ""), "/about/"))
    nf = render(tpl("simple.html"), {"heading": "找不到這個頁面",
                                      "body": '<p>網址可能已變更，請回到<a href="/">首頁</a>查看最新文章。</p>'})
    write("404.html", page(nf, "找不到頁面", CFG.get("description", ""), "/404.html"))

    # sitemap / RSS / robots
    # sitemap 收錄所有頁面（含分頁），並標上最後更新日期
    def pages_of(prefix, count):
        total = max(1, -(-count // PER_PAGE))
        return [prefix] + [f"{prefix}page/{i}/" for i in range(2, total + 1)]

    def newest(items):
        return max((p.get("updated", p["date"]) for p in items), default="")

    entries = [(u, newest(posts)) for u in pages_of("/", len(posts))] + [("/about/", "")]
    for key in CFG.get("categories", {}):
        in_cat = [p for p in posts if p["category"] == key]
        entries += [(u, newest(in_cat)) for u in pages_of(f"/category/{key}/", len(in_cat))]
    entries += [(p["url"], p.get("updated", p["date"])) for p in posts]
    sm = "".join(f"  <url><loc>{BASE}{u}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>\n"
                 for u, d in entries)
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n'
                         f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{sm}</urlset>\n')
    items = "".join(
        f"<item><title>{esc(p['title'])}</title><link>{BASE}{p['url']}</link><guid>{BASE}{p['url']}</guid>"
        f"<pubDate>{datetime.strptime(p['date'], '%Y-%m-%d').strftime('%a, %d %b %Y 00:00:00 +0800')}</pubDate>"
        f"<description>{esc(p.get('description', ''))}</description></item>" for p in posts[:20])
    write("feed.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
                      f"<title>{esc(CFG['site_name'])}</title><link>{BASE}/</link>"
                      f"<description>{esc(CFG.get('description', ''))}</description>{items}</channel></rss>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    print(f"完成：{len(posts)} 篇文章 -> {OUT}")


def new_post(slug, title):
    today = date.today().isoformat()
    path = POSTS / f"{today}-{slug}.html"
    if path.exists():
        raise SystemExit(f"已存在：{path}")
    path.write_text(
        f"---\ntitle: {title}\ndate: {today}\ncategory: {CFG.get('default_category', 'guide')}\n"
        f"description: 一句話摘要（約 60 字，會顯示在列表與搜尋結果）\n"
        f"image: /images/{slug}.jpg\nimage_alt: {title}\ndraft: true\n---\n"
        f"<p>開頭段落。</p>\n\n<h2>小標題</h2>\n<p>內文。</p>\n<ul>\n<li>重點一</li>\n<li>重點二</li>\n</ul>\n",
        "utf-8", newline="\n")
    print(f"已建立草稿：{path}\n寫完後把 draft: true 改成 false，再執行 python build.py")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["new"] and len(args) >= 3:
        new_post(args[1], " ".join(args[2:]))
    elif args[:1] == ["serve"]:
        build()
        import functools, http.server
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
        print("預覽：http://localhost:8000 （Ctrl+C 結束）")
        http.server.ThreadingHTTPServer(("127.0.0.1", 8000), handler).serve_forever()
    else:
        build()
