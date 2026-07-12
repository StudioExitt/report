#!/usr/bin/env python3
"""
update_index.py — index.html의 ITEMS / CATEGORY_META를 자동 갱신합니다.

- docs/ 하위 디렉토리를 전부 스캔해 .html 파일이 있는 디렉토리를 카테고리로 인식
  (하드코딩된 카테고리 목록 없음 — 새 디렉토리를 추가하면 자동으로 반영됨)
- index.html에 누락된 파일을 찾아 추가, 삭제된 파일은 제거
- 날짜 기준 내림차순 정렬 (최신 파일이 앞)
- 파일명 패턴: {category}_{YYYY-MM-DD}_{title}.html
- 제목은 <title> 태그 → <h1> 태그 → 파일명 순으로 추출
- 새로 발견된 카테고리에는 팔레트에서 아이콘/색상을 자동 배정
"""

import re
import json
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

DOCS_DIR = Path(__file__).parent
INDEX_PATH = DOCS_DIR / "index.html"
EXCLUDE_FILES = {"index.html"}
EXCLUDE_DIRS = {"assets", "static", "img", "images", "css", "js"}

DATA_BEGIN = "/* DATA:BEGIN */"
DATA_END = "/* DATA:END */"

# 알려진 카테고리의 기본 메타 (라벨/아이콘/색상). 여기 없는 카테고리는 팔레트에서 자동 배정.
KNOWN_META = {
    "daily": {"label": "Daily", "icon": "📰", "color": "#0e7d5a", "bg": "#ecfdf5"},
    "study": {"label": "Study", "icon": "📚", "color": "#1a56a0", "bg": "#eff6ff"},
    "tech":  {"label": "Tech",  "icon": "💻", "color": "#7c3aed", "bg": "#f5f3ff"},
}

# 새로 발견되는 카테고리에 순서대로 배정할 색상 팔레트
PALETTE = [
    {"icon": "📄", "color": "#c2410c", "bg": "#fff7ed"},
    {"icon": "🗂️", "color": "#0891b2", "bg": "#ecfeff"},
    {"icon": "🎯", "color": "#be123c", "bg": "#fff1f2"},
    {"icon": "🌱", "color": "#4d7c0f", "bg": "#f7fee7"},
    {"icon": "🧪", "color": "#a16207", "bg": "#fefce8"},
    {"icon": "🛠️", "color": "#334155", "bg": "#f8fafc"},
]

# 고정 노출 순서 (있으면 먼저, 나머지는 알파벳 순으로 뒤에 붙음)
PREFERRED_ORDER = ["daily", "study", "tech"]


class TitleExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.in_h1 = False
        self.title = None
        self.h1 = None

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        elif tag == "h1" and self.h1 is None:
            self.in_h1 = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "h1":
            self.in_h1 = False

    def handle_data(self, data):
        if self.in_title and self.title is None:
            self.title = data.strip()
        elif self.in_h1 and self.h1 is None:
            self.h1 = data.strip()


def extract_title(html_path: Path) -> str:
    """HTML 파일에서 제목을 추출합니다.

    daily 파일은 <title>이 날짜 형식의 범용 제목이므로 파일명을 우선 사용.
    그 외 카테고리는 <title> → <h1> → 파일명 순으로 시도.
    """
    stem_title = stem_to_title(html_path.stem)
    if html_path.parent.name == "daily":
        return stem_title

    parser = TitleExtractor()
    try:
        text = html_path.read_text(encoding="utf-8", errors="ignore")
        parser.feed(text)
    except Exception:
        pass
    return parser.title or parser.h1 or stem_title


def stem_to_title(stem: str) -> str:
    """파일명 stem에서 읽기 좋은 제목을 생성합니다."""
    # 패턴: study_2026-06-12_제목 → 제목 부분만
    parts = stem.split("_", 2)
    if len(parts) >= 3:
        return parts[2].replace("-", " ").replace("_", " ")
    return stem


def extract_date_from_stem(stem: str) -> Optional[str]:
    """파일명에서 YYYY-MM-DD 날짜를 추출합니다."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", stem)
    return m.group(1) if m else None


def dir_to_label(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").title()


def discover_categories(docs_dir: Path) -> list[str]:
    """docs/ 하위에서 .html 파일을 가진 디렉토리를 카테고리로 인식합니다."""
    cats = []
    for sub in sorted(docs_dir.iterdir()):
        if not sub.is_dir() or sub.name.startswith(".") or sub.name in EXCLUDE_DIRS:
            continue
        if any(f.name not in EXCLUDE_FILES for f in sub.glob("*.html")):
            cats.append(sub.name)
    ordered = [c for c in PREFERRED_ORDER if c in cats]
    ordered += sorted(c for c in cats if c not in PREFERRED_ORDER)
    return ordered


def scan_category(docs_dir: Path, cat: str) -> list[dict]:
    items = []
    for html_file in sorted((docs_dir / cat).glob("*.html")):
        if html_file.name in EXCLUDE_FILES:
            continue
        stem = html_file.stem
        date_str = extract_date_from_stem(stem)
        if date_str is None:
            mtime = html_file.stat().st_mtime
            date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        title = extract_title(html_file)
        rel_path = f"{cat}/{html_file.name}"
        items.append({"date": date_str, "title": title, "file": rel_path})
    return items


def extract_data_block(index_html: str) -> str:
    start = index_html.index(DATA_BEGIN) + len(DATA_BEGIN)
    end = index_html.index(DATA_END)
    return index_html[start:end]


def parse_existing_meta(data_block: str) -> dict[str, dict]:
    m = re.search(r"CATEGORY_META\s*=\s*(\{.*?\n\s*\});", data_block, re.DOTALL)
    if not m:
        return {}
    meta = {}
    for entry_m in re.finditer(r"(\w+):\s*\{([^{}]*)\}", m.group(1)):
        cat, body = entry_m.group(1), entry_m.group(2)
        fields = {}
        for field in ("label", "icon", "color", "bg"):
            fm = re.search(rf"{field}\s*:\s*'([^']*)'", body)
            if fm:
                fields[field] = fm.group(1)
        if fields:
            meta[cat] = fields
    return meta


def parse_existing_items(data_block: str) -> dict[str, list[dict]]:
    m = re.search(r"ITEMS\s*=\s*(\{.*?\n\s*\});", data_block, re.DOTALL)
    if not m:
        return {}
    body = m.group(1)
    result = {}
    for entry_m in re.finditer(r"(\w+):\s*\[([^\[\]]*)\],?\s*\n", body):
        cat, arr_body = entry_m.group(1), entry_m.group(2)
        items = []
        for obj_m in re.finditer(r"\{([^{}]+)\}", arr_body, re.DOTALL):
            obj_str = obj_m.group(1)
            item = {}
            for field in ("date", "title", "file"):
                fm = re.search(rf"{field}\s*:\s*'((?:[^'\\]|\\.)*)'", obj_str)
                if fm:
                    item[field] = fm.group(1).replace("\\'", "'")
            if "file" in item:
                items.append(item)
        result[cat] = items
    return result


def build_meta(categories: list[str], existing_meta: dict[str, dict]) -> dict[str, dict]:
    meta = {}
    palette_i = 0
    for cat in categories:
        if cat in existing_meta:
            meta[cat] = existing_meta[cat]
        elif cat in KNOWN_META:
            meta[cat] = KNOWN_META[cat]
        else:
            palette = PALETTE[palette_i % len(PALETTE)]
            palette_i += 1
            meta[cat] = {"label": dir_to_label(cat), **palette}
    return meta


def js_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def items_to_js(items: list[dict], indent: int = 6) -> str:
    if not items:
        return "[]"
    pad = " " * indent
    lines = ["["]
    for item in items:
        lines.append(f"{pad}{{")
        lines.append(f"{pad}  date: '{js_str(item['date'])}',")
        lines.append(f"{pad}  title: '{js_str(item['title'])}',")
        lines.append(f"{pad}  file: '{js_str(item['file'])}',")
        lines.append(f"{pad}}},")
    lines.append(f"{' ' * (indent - 2)}]")
    return "\n".join(lines)


def render_data_block(today_str: str, meta: dict[str, dict], items_by_cat: dict[str, list[dict]]) -> str:
    lines = []
    lines.append(f"  const TODAY = '{today_str}';")
    lines.append("")
    lines.append("  const CATEGORY_META = {")
    for cat, m in meta.items():
        lines.append(
            f"    {cat}: {{ label: '{js_str(m['label'])}', icon: '{m['icon']}', "
            f"color: '{m['color']}', bg: '{m['bg']}' }},"
        )
    lines.append("  };")
    lines.append("")
    lines.append("  const ITEMS = {")
    for cat, items in items_by_cat.items():
        lines.append(f"    {cat}: {items_to_js(items)},")
    lines.append("  };")
    return "\n".join(lines)


CATEGORY_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{label} · Reports</title>
  <link rel="icon" type="image/png" href="../favicon.png">
  <style>
    :root {{
      --primary: #1a56a0;
      --primary-dark: #0f2d5c;
      --secondary: #0e7d5a;
      --bg: #f4f6fa;
      --card: #ffffff;
      --text: #1e2430;
      --muted: #6b7280;
      --border: #e5e7eb;
      --cat-color: {color};
      --cat-bg: {bg};
      --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.04);
      --shadow-hover: 0 4px 12px rgba(0,0,0,0.12), 0 8px 24px rgba(0,0,0,0.06);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', 'Segoe UI', sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      min-height: 100vh;
    }}
    .site-header {{
      background: linear-gradient(135deg, var(--primary-dark) 0%, var(--primary) 60%, var(--secondary) 100%);
      color: white;
      padding: 48px 24px 40px;
      text-align: center;
    }}
    .site-header .back {{
      display: inline-block;
      margin-bottom: 14px;
      font-size: 0.85rem;
      color: rgba(255,255,255,0.85);
      text-decoration: none;
    }}
    .site-header .back:hover {{ text-decoration: underline; }}
    .site-header h1 {{
      font-size: 2rem;
      font-weight: 800;
      letter-spacing: -0.5px;
    }}
    .stats {{
      display: flex;
      justify-content: center;
      padding: 24px 24px 4px;
      font-size: 0.85rem;
      color: var(--muted);
    }}
    .stats strong {{ font-size: 1.1rem; font-weight: 700; color: var(--text); margin-right: 4px; }}
    main {{ max-width: 860px; margin: 0 auto; padding: 24px 24px 64px; }}
    .card-list {{ display: flex; flex-direction: column; gap: 10px; margin-top: 20px; }}
    .card {{
      display: flex;
      align-items: center;
      background: var(--card);
      border-radius: 14px;
      padding: 18px 20px;
      box-shadow: var(--shadow);
      text-decoration: none;
      color: inherit;
      transition: all 0.18s;
      border: 1.5px solid transparent;
      gap: 16px;
    }}
    .card:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-hover); border-color: var(--cat-bg); }}
    .card-icon {{
      width: 44px; height: 44px; border-radius: 12px;
      display: flex; align-items: center; justify-content: center;
      font-size: 1.3rem; flex-shrink: 0; background: var(--cat-bg);
    }}
    .card-body {{ flex: 1; min-width: 0; }}
    .card-title {{
      font-size: 0.97rem; font-weight: 600; color: var(--text);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 3px;
    }}
    .card-meta {{ font-size: 0.8rem; color: var(--muted); display: flex; align-items: center; gap: 10px; }}
    .new-badge {{
      background: #fef3c7; color: #92400e; font-size: 0.68rem; font-weight: 800;
      padding: 1px 7px; border-radius: 9999px; letter-spacing: 0.05em;
    }}
    .card-arrow {{ color: var(--border); font-size: 1.1rem; flex-shrink: 0; transition: color 0.18s, transform 0.18s; }}
    .card:hover .card-arrow {{ color: var(--muted); transform: translateX(3px); }}
    .empty {{ text-align: center; padding: 48px 24px; color: var(--muted); font-size: 0.9rem; }}
    .empty .emoji {{ font-size: 2.5rem; margin-bottom: 12px; }}
    footer {{ text-align: center; padding: 28px; color: var(--muted); font-size: 0.78rem; border-top: 1px solid var(--border); }}
    @media (max-width: 600px) {{ .site-header h1 {{ font-size: 1.5rem; }} .card-title {{ font-size: 0.9rem; }} }}
  </style>
</head>
<body>
<header class="site-header">
  <a class="back" href="../index.html">&larr; 전체 보기</a>
  <h1>{icon} {label}</h1>
</header>
<div class="stats"><strong>{count}</strong>개 문서</div>
<main>
  <div class="card-list">
{cards}
  </div>
</main>
<footer>&copy; 2026 StudioExitt Reports &middot; 마지막 업데이트: {today}</footer>
</body>
</html>
"""


def is_new(item_date: str, today_str: str) -> bool:
    d1 = datetime.strptime(today_str, "%Y-%m-%d")
    d2 = datetime.strptime(item_date, "%Y-%m-%d")
    return (d1 - d2).days <= 3


def render_category_card(item: dict, meta: dict, today_str: str) -> str:
    filename = item["file"].split("/", 1)[1]
    new_badge = '<span class="new-badge">NEW</span>' if is_new(item["date"], today_str) else ""
    return f"""    <a href="{filename}" class="card">
      <div class="card-icon">{meta['icon']}</div>
      <div class="card-body">
        <div class="card-meta">
          <span>{item['date']}</span>
          {new_badge}
        </div>
        <div class="card-title">{item['title']}</div>
      </div>
      <span class="card-arrow">&rsaquo;</span>
    </a>"""


def render_category_page(cat: str, meta: dict, items: list[dict], today_str: str) -> str:
    if items:
        cards = "\n".join(render_category_card(item, meta, today_str) for item in items)
    else:
        cards = f'    <div class="empty"><div class="emoji">📭</div>{meta["label"]} 문서가 아직 없습니다.</div>'
    return CATEGORY_PAGE_TEMPLATE.format(
        label=meta["label"], icon=meta["icon"], color=meta["color"], bg=meta["bg"],
        count=len(items), cards=cards, today=today_str,
    )


def write_category_pages(docs_dir: Path, meta: dict[str, dict], items_by_cat: dict[str, list[dict]],
                          today_str: str, report_lines: list) -> None:
    for cat, items in items_by_cat.items():
        page_path = docs_dir / cat / "index.html"
        new_html = render_category_page(cat, meta[cat], items, today_str)
        if not page_path.exists() or page_path.read_text(encoding="utf-8") != new_html:
            page_path.write_text(new_html, encoding="utf-8")
            report_lines.append(f"[{cat}] {page_path.relative_to(docs_dir)} 갱신")


def update_index(docs_dir: Path, index_path: Path) -> None:
    index_html = index_path.read_text(encoding="utf-8")
    today_str = date.today().strftime("%Y-%m-%d")

    data_block = extract_data_block(index_html)
    existing_meta = parse_existing_meta(data_block)
    existing_items = parse_existing_items(data_block)

    discovered = discover_categories(docs_dir)
    # 기존에 있었지만 이번 스캔에 없는 카테고리(디렉토리 삭제 등)도 일단 후보에 포함
    all_cats = list(discovered) + [c for c in existing_items if c not in discovered]

    report_lines = []
    new_categories = [c for c in discovered if c not in existing_items]
    if new_categories:
        report_lines.append(f"새로운 카테고리 발견: {', '.join(new_categories)}")

    items_by_cat = {}
    for cat in all_cats:
        scanned = scan_category(docs_dir, cat) if cat in discovered else []
        scanned_by_file = {item["file"]: item for item in scanned}

        updated_existing = []
        for item in existing_items.get(cat, []):
            actual = docs_dir / item["file"]
            if not actual.exists():
                report_lines.append(f"[{cat}] 파일 없음 → 삭제: {item['file']}")
                continue
            fresh = scanned_by_file.get(item["file"])
            if fresh and fresh["title"] != item.get("title"):
                report_lines.append(f"[{cat}] 제목 갱신: {item['file']}")
                report_lines.append(f"  전: {item.get('title')}")
                report_lines.append(f"  후: {fresh['title']}")
                updated_existing.append(fresh)
            else:
                updated_existing.append(item)

        existing_files = {item["file"] for item in existing_items.get(cat, [])}
        added = [item for item in scanned if item["file"] not in existing_files]
        if added:
            report_lines.append(f"[{cat}] 새로 추가된 파일 {len(added)}개:")
            for a in added:
                report_lines.append(f"  + {a['file']}  ({a['date']}) {a['title']}")

        merged = updated_existing + added
        merged.sort(key=lambda x: (x.get("date", ""), x.get("file", "")), reverse=True)
        if merged:
            items_by_cat[cat] = merged
        elif cat in existing_items:
            report_lines.append(f"[{cat}] 항목이 모두 사라져 카테고리를 제거합니다.")

    meta = build_meta(list(items_by_cat.keys()), existing_meta)
    write_category_pages(docs_dir, meta, items_by_cat, today_str, report_lines)
    new_data_block = "\n" + render_data_block(today_str, meta, items_by_cat) + "\n  "

    changed = new_data_block.strip() != data_block.strip() or bool(report_lines)
    new_index_html = index_html[: index_html.index(DATA_BEGIN) + len(DATA_BEGIN)] + \
        new_data_block + \
        index_html[index_html.index(DATA_END):]

    if new_index_html != index_html:
        index_path.write_text(new_index_html, encoding="utf-8")
        print("index.html 업데이트 완료")
    else:
        print("변경 사항 없음 — index.html은 최신 상태입니다.")

    for line in report_lines:
        print(line)

    print()
    print("=== 전체 현황 ===")
    for cat, items in items_by_cat.items():
        print(f"[{cat}] {len(items)}개")
        for item in items:
            print(f"  {item['date']}  {item['title']}")


if __name__ == "__main__":
    update_index(DOCS_DIR, INDEX_PATH)
