import json, re

with open('dujiangyan_wap.html', encoding='utf-8') as f:
    html = f.read()
m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
pd = json.loads(m.group(1))['props']['pageProps']['pageData']

def txt(nodes):
    out = []
    if isinstance(nodes, str):
        return nodes
    if isinstance(nodes, dict):
        nodes = [nodes]
    for n in nodes or []:
        if not isinstance(n, dict):
            out.append(str(n))
            continue
        if 'text' in n and isinstance(n['text'], str):
            out.append(n['text'])
        elif 'content' in n:
            out.append(txt(n['content']))
    return ''.join(out)

L = []
L.append('# ' + pd['lemmaTitle'])
L.append('')
L.append('> ' + pd['lemmaDesc'])
L.append('')

# ---------- infobox ----------
card = pd.get('card') or {}
items = card.get('content') or []
if items:
    L.append('## 基本信息栏')
    L.append('')
    for it in items:
        name = it.get('title') or it.get('key') or ''
        vals = []
        for d in (it.get('data') or []):
            t = txt(d.get('text')).strip()
            if t:
                vals.append(t)
        if name and vals:
            sep = '；' if it.get('isArray') else ''
            L.append(f'- **{name}**：{sep.join(vals)}')
    L.append('')

# ---------- abstract ----------
ab = pd.get('abstract') or []
if ab:
    L.append('## 内容简介（摘要）')
    L.append('')
    for blk in ab:
        t = txt(blk.get('content')).strip()
        if t:
            L.append(t)
    L.append('')

# ---------- catalogue ----------
cat = pd.get('catalog') or []
if cat:
    L.append('## 目录')
    L.append('')
    for c in cat:
        L.append('  ' * (c.get('level', 1) - 1) + f"- {c.get('title','')}")
    L.append('')

# ---------- body ----------
L.append('## 正文')
L.append('')

def emit_item(it):
    tag = it.get('tag')
    if tag == 'header':
        lvl = min(6, (it.get('level') or 1) + 1)
        L.append('')
        L.append('#' * lvl + ' ' + it.get('title', ''))
        L.append('')
    elif tag == 'paragraph':
        t = txt(it.get('content')).strip()
        if t:
            L.append(t)
            L.append('')
    elif tag == 'list':
        for li in it.get('items', []):
            t = txt(li.get('content')).strip()
            if t:
                L.append('- ' + t)
        L.append('')
    elif tag == 'module':
        ty = it.get('type')
        c = it.get('content') or {}
        if ty == 'table':
            cap = c.get('caption')
            if cap:
                L.append(f'**{cap}**')
                L.append('')
            for row in c.get('rows', []):
                cells = []
                for cell in row.get('cells', []):
                    if cell.get('type') == 'spanholder':
                        continue
                    ct = ' '.join(txt(p.get('content')).strip() for p in (cell.get('content') or []))
                    cells.append(ct.replace('\n', ' ').strip())
                if any(cells):
                    L.append('| ' + ' | '.join(cells) + ' |')
            L.append('')
        elif ty == 'map':
            if c.get('title'):
                L.append(f"> 地图位置：{c.get('title')}（{c.get('address','')}；经纬度 {c.get('lng')}, {c.get('lat')}）")
                L.append('')
        elif ty == 'album':
            descs = []
            for im in (c.get('content') or []):
                d = im.get('desc')
                if d and d not in descs:
                    descs.append(d)
            if descs:
                L.append('> 图集：' + '、'.join(descs) + f'（共{c.get("total","")}张）')
                L.append('')
        elif ty == 'albumCollection':
            descs = []
            for al in (c.get('albums') or []):
                d = (al.get('content') or {}).get('desc')
                if d:
                    descs.append(d)
            if descs:
                L.append('> 图集分组：' + '、'.join(descs))
                L.append('')

for sec in pd.get('structuredContent') or []:
    for it in sec:
        emit_item(it)

# ---------- references ----------
refs = pd.get('reference') or []
if refs:
    L.append('')
    L.append('## 参考资料')
    L.append('')
    for r in refs:
        L.append(f"{r.get('index','')}. {r.get('site','')} — {r.get('title','')}（{r.get('refDate','')}）")

text = '\n'.join(L)
text = re.sub(r'\n{3,}', '\n\n', text)

with open('都江堰_百度百科.md', 'w', encoding='utf-8') as f:
    f.write(text)

print('总字符数:', len(text))
print(text[:2200])
print('...')
print(text[-1800:])
