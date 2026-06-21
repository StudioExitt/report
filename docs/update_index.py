#!/usr/bin/env python3
"""
update_index.py — index.html의 studyItems / dailyItems 배열을 자동 갱신합니다.

- docs/ 하위 디렉토리(study/, daily/ 등)의 HTML 파일을 스캔
- index.html에 누락된 파일을 찾아 추가
- 날짜 기준 내림차순 정렬 (최신 파일이 앞)
- 파일명 패턴: {category}_{YYYY-MM-DD}_{title}.html
- 제목은 <title> 태그 → <h1> 태그 → 파일명 순으로 추출
"""

import os
import re
import json
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

DOCS_DIR = Path(__file__).parent
INDEX_PATH = DOCS_DIR / "index.html"
EXCLUDE_FILES = {"index.html"}
KNOWN_CATEGORIES = ["daily", "study", "tech"]

# 카테고리별 JS 변수명 매핑
CATEGORY_VAR = {
    "daily": "dailyItems",
    "study": "studyItems",
    "tech":  "techItems",
}


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
    study 파일은 <title> → <h1> → 파일명 순으로 시도.
    """
    stem_title = stem_to_title(html_path.stem)
    # daily: 파일명에 실제 내용이 담겨 있으므로 바로 반환
    if html_path.parent.name in ("daily",):
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


def scan_html_files(docs_dir: Path) -> dict[str, list[dict]]:
    """하위 디렉토리의 HTML 파일을 카테고리별로 스캔합니다."""
    found: dict[str, list[dict]] = {}
    for sub in sorted(docs_dir.iterdir()):
        if not sub.is_dir():
            continue
        cat = sub.name
        if cat not in KNOWN_CATEGORIES:
            continue
        items = []
        for html_file in sorted(sub.glob("*.html")):
            if html_file.name in EXCLUDE_FILES:
                continue
            stem = html_file.stem
            date_str = extract_date_from_stem(stem)
            if date_str is None:
                # 날짜 없으면 파일 수정 시간 사용
                mtime = html_file.stat().st_mtime
                from datetime import datetime
                date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            title = extract_title(html_file)
            rel_path = f"{cat}/{html_file.name}"
            items.append({"date": date_str, "title": title, "file": rel_path})
        if items:
            found[cat] = items
    return found


def parse_existing_items(index_html: str, var_name: str) -> list[dict]:
    """index.html의 JS 배열에서 기존 항목을 파싱합니다."""
    pattern = rf"const\s+{re.escape(var_name)}\s*=\s*(\[.*?\]);"
    m = re.search(pattern, index_html, re.DOTALL)
    if not m:
        return []
    try:
        # JS 객체를 JSON으로 변환 (trailing comma 제거)
        js_array = m.group(1)
        js_array = re.sub(r",\s*}", "}", js_array)   # trailing comma in object
        js_array = re.sub(r",\s*\]", "]", js_array)  # trailing comma in array
        return json.loads(js_array)
    except json.JSONDecodeError:
        # 직접 파싱
        items = []
        for obj_m in re.finditer(r"\{([^}]+)\}", js_array, re.DOTALL):
            obj_str = obj_m.group(1)
            item = {}
            for field in ("date", "title", "file"):
                fm = re.search(rf"['\"]?{field}['\"]?\s*:\s*'([^']*)'", obj_str)
                if not fm:
                    fm = re.search(rf'[\'"]?{field}[\'"]?\s*:\s*"([^"]*)"', obj_str)
                if fm:
                    item[field] = fm.group(1)
            if "file" in item:
                items.append(item)
        return items


def items_to_js(items: list[dict], indent: int = 4) -> str:
    """아이템 목록을 JS 배열 문자열로 변환합니다."""
    if not items:
        return "[]"
    pad = " " * indent
    lines = ["["]
    for item in items:
        # JSON 직렬화 후 JS 스타일로 변환 (싱글쿼트)
        file_val = item["file"].replace("'", "\\'")
        title_val = item["title"].replace("'", "\\'")
        lines.append(f"{pad}{{")
        lines.append(f"{pad}  date: '{item['date']}',")
        lines.append(f"{pad}  title: '{title_val}',")
        lines.append(f"{pad}  file: '{file_val}',")
        lines.append(f"{pad}}},")
    lines.append(f"{' ' * (indent - 4)}]")
    return "\n".join(lines)


def update_index(docs_dir: Path, index_path: Path) -> None:
    index_html = index_path.read_text(encoding="utf-8")

    scanned = scan_html_files(docs_dir)
    today_str = date.today().strftime("%Y-%m-%d")

    changed = False
    report_lines = []

    for cat in KNOWN_CATEGORIES:
        var_name = CATEGORY_VAR[cat]
        existing = parse_existing_items(index_html, var_name)
        existing_files = {item["file"] for item in existing}

        new_from_scan = scanned.get(cat, [])
        scanned_by_file = {item["file"]: item for item in new_from_scan}

        # 기존 항목: 실제 파일 없으면 제거, 제목 변경 시 갱신
        updated_existing = []
        for item in existing:
            actual = docs_dir / item["file"]
            if not actual.exists():
                report_lines.append(f"[{cat}] 파일 없음 → 삭제: {item['file']}")
                changed = True
                continue
            fresh = scanned_by_file.get(item["file"])
            if fresh and fresh["title"] != item.get("title"):
                report_lines.append(f"[{cat}] 제목 갱신: {item['file']}")
                report_lines.append(f"  전: {item.get('title')}")
                report_lines.append(f"  후: {fresh['title']}")
                updated_existing.append(fresh)
                changed = True
            else:
                updated_existing.append(item)

        added = []
        for item in new_from_scan:
            if item["file"] not in existing_files:
                added.append(item)

        if added:
            report_lines.append(f"[{cat}] 새로 추가된 파일 {len(added)}개:")
            for a in added:
                report_lines.append(f"  + {a['file']}  ({a['date']}) {a['title']}")
            changed = True

        merged = updated_existing + added
        # 날짜 내림차순 정렬, 같은 날짜면 파일명 역순
        merged.sort(key=lambda x: (x.get("date", ""), x.get("file", "")), reverse=True)

        # JS 배열 교체
        new_js = items_to_js(merged, indent=4)
        pattern = rf"(const\s+{re.escape(var_name)}\s*=\s*)(\[.*?\])(\s*;)"
        replacement = rf"\g<1>{new_js}\g<3>"
        new_html = re.sub(pattern, replacement, index_html, flags=re.DOTALL)
        if new_html != index_html:
            index_html = new_html
            if not added:
                report_lines.append(f"[{cat}] 순서 재정렬 완료")
            changed = True

    # TODAY 상수 갱신
    old_today_m = re.search(r"const TODAY = '(\d{4}-\d{2}-\d{2})'", index_html)
    if old_today_m and old_today_m.group(1) != today_str:
        index_html = index_html.replace(
            f"const TODAY = '{old_today_m.group(1)}'",
            f"const TODAY = '{today_str}'"
        )
        report_lines.append(f"TODAY 갱신: {old_today_m.group(1)} → {today_str}")
        changed = True

    if changed:
        index_path.write_text(index_html, encoding="utf-8")
        print("index.html 업데이트 완료")
    else:
        print("변경 사항 없음 — index.html은 최신 상태입니다.")

    for line in report_lines:
        print(line)

    # 누락 없이 전체 현황 출력
    print()
    print("=== 전체 현황 ===")
    for cat in KNOWN_CATEGORIES:
        var_name = CATEGORY_VAR[cat]
        final = parse_existing_items(index_path.read_text(encoding="utf-8"), var_name)
        print(f"[{cat}] {len(final)}개")
        for item in final:
            print(f"  {item['date']}  {item['title']}")


if __name__ == "__main__":
    update_index(DOCS_DIR, INDEX_PATH)
