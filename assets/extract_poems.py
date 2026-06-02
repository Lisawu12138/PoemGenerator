"""
海子诗全集 PDF 提取工具 v4 - 最终版
宽松提取 + 严格后处理 + 内容去重
"""

import pdfplumber
import json
import re
from collections import Counter

PDF_PATH = r"c:\Users\tianmacheng\Desktop\test\PoemGenerator\海子诗全集.pdf"
OUTPUT_PATH = r"c:\Users\tianmacheng\Desktop\test\PoemGenerator\haizi_poems.json"

SECTION_HEADERS = [
    (r"第一编\s*短诗", "短诗（1983～1986）"),
    (r"第二编\s*长诗", "长诗（1984～1985）"),
    (r"第三编\s*短诗", "短诗（1987～1989）"),
    (r"第四编\s*太阳", "太阳·七部书（1986～1988）"),
    (r"第五编\s*文论", "文论"),
    (r"第六编\s*补遗", "补遗"),
]

DATE_PATTERN = re.compile(r'^(\d{4})[\.\-年](\d{1,2})?[\.\-月]?(\d{1,2})?[日]?$')


def is_section_header(text):
    for pattern, name in SECTION_HEADERS:
        if re.search(pattern, text.strip()):
            return name
    return None


def is_date_line(text):
    return DATE_PATTERN.match(text.strip()) is not None


def extract_date(text):
    text = text.strip()
    m = DATE_PATTERN.match(text)
    if m:
        year = m.group(1)
        month = m.group(2) if m.group(2) else ""
        return f"{year}" + (f".{month}" if month else "")
    return None


def should_exclude_title(title):
    """后处理阶段排除非诗歌标题"""
    title = title.strip()

    # 结构标题模式
    struct_patterns = [
        r'^第[一二三四五六七八九十百]+[幕场章辑]',
        r'^[1-9]\．',
        r'^[1-9]月。',
        r'^[a-e]：',
        r'^（有题无诗）',
        r'^幕间过场',
    ]
    for pat in struct_patterns:
        if re.match(pat, title):
            return True

    exclude_set = {
        # 太阳七部书结构
        "序幕", "太阳·断头篇", "太阳·土地篇", "太阳·大札撒",
        "太阳·弑", "太阳·诗剧", "太阳·弥赛亚",
        "太阳·你是父亲的好女儿", "抒情诗",
        "《大草原》三部曲之一",
        # 补遗结构
        "第一辑：给土地", "第二辑：静物",
        "第三辑：故乡四题", "第四辑：远山风景",
        "第五辑：告别的两端",
        "小站", "后记", "麦地之瓮", "散佚作品",
        "以山的名义，兄弟们（组诗）",
        # 文论
        "寻找对实体的接触", "源头和鸟", "民间主题",
        "寂静", "动作", "诗学：一份提纲",
        "我热爱的诗人——荷尔德林",
        "死亡后记", "编后记", "日记",
        # 广告/非诗歌
        "海量电子版、纸质版书籍及音频课程",
    }
    if title in exclude_set:
        return True

    # 文论标题前缀
    for prefix in ["寻找对实体的接触", "源头和鸟", "民间主题", "寂静", "动作"]:
        if title.startswith(prefix):
            return True

    # 广告类内容
    if "微信" in title or "电子版" in title:
        return True

    # 太阳七部书中的一些长标题（明显是戏剧台词标识）
    if title.startswith("甲：") or title.startswith("乙："):
        return True

    return False


def should_exclude_content(content):
    """根据内容排除非诗歌"""
    # 广告
    if "微信：" in content or "电子版" in content:
        return True
    return False


def is_near_duplicate(content1, content2, threshold=0.8):
    """检查两段内容是否近似重复"""
    if not content1 or not content2:
        return False
    # 使用简单的子串匹配：如果较短内容的80%以上出现在较长内容中
    short, long = (content1, content2) if len(content1) <= len(content2) else (content2, content1)
    # 检查前30字是否相同
    if short[:30] == long[:30]:
        return True
    return False


def extract_all_text(pdf_path):
    all_pages = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"PDF总页数: {total}")
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            all_pages.append({"page_num": i + 1, "text": text if text else ""})
            if (i + 1) % 200 == 0:
                print(f"  已提取 {i+1}/{total} 页...")
    return all_pages


def find_section_boundaries(pages):
    boundaries = {}
    for i, page in enumerate(pages):
        section_name = is_section_header(page["text"])
        if section_name:
            boundaries.setdefault(section_name, []).append(i)

    result = {}
    for name, page_list in boundaries.items():
        if len(page_list) > 1:
            result[name] = page_list[1]
        else:
            result[name] = page_list[0]
    return result


def parse_poems_from_section(pages, start_page, end_page, section_name):
    poems = []
    full_text = ""
    for i in range(start_page, end_page):
        full_text += pages[i]["text"] + "\n\n"

    lines = full_text.split("\n")
    current_poem = None
    prev_line_empty = True

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            prev_line_empty = True
            i += 1
            continue

        if re.match(r'^\d+$', line):
            i += 1
            continue

        if is_section_header(line):
            i += 1
            continue

        # 脚注分隔线
        if re.match(r'^—{3,}$', line) and len(line) <= 60:
            i += 1
            while i < len(lines):
                fl = lines[i].strip() if i < len(lines) else ""
                if not fl:
                    break
                if re.match(r'^\d+\)', fl) or re.match(r'^\(\d+\)', fl):
                    i += 1
                else:
                    break
            continue

        # 脚注
        if re.match(r'^\d+\)', line) or re.match(r'^\(\d+\)', line):
            i += 1
            continue

        # 日期行
        if is_date_line(line):
            if current_poem:
                date = extract_date(line)
                if date:
                    current_poem["date"] = date
                poems.append(current_poem)
                current_poem = None
            prev_line_empty = True
            i += 1
            continue

        # 标题判断
        is_title = False
        if len(line) <= 25 and prev_line_empty:
            has_content_after = False
            for j in range(i + 1, min(i + 6, len(lines))):
                nl = lines[j].strip()
                if nl and not re.match(r'^\d+$', nl) and not is_date_line(nl):
                    has_content_after = True
                    break

            if has_content_after:
                if current_poem is None:
                    is_title = True
                elif len(line) <= 22:
                    is_title = True

        if is_title:
            if current_poem:
                poems.append(current_poem)
            current_poem = {
                "title": line,
                "content": "",
                "date": "",
                "section": section_name
            }
        else:
            cleaned = re.sub(r'\s*\(\d+\)\s*$', '', line).strip()
            if cleaned:
                if current_poem:
                    if current_poem["content"]:
                        current_poem["content"] += "\n" + cleaned
                    else:
                        current_poem["content"] = cleaned

        prev_line_empty = False if line else True
        i += 1

    if current_poem:
        poems.append(current_poem)

    return poems


def main():
    print("=" * 60)
    print("海子诗全集 PDF 提取工具 v4 (最终版)")
    print("=" * 60)

    print("\n[1/4] 提取PDF文本...")
    pages = extract_all_text(PDF_PATH)

    print("\n[2/4] 识别编目结构...")
    boundaries = find_section_boundaries(pages)
    for name, page_idx in sorted(boundaries.items(), key=lambda x: x[1]):
        print(f"  {name}: 第 {page_idx + 1} 页")

    section_order = [
        "短诗（1983～1986）",
        "长诗（1984～1985）",
        "短诗（1987～1989）",
        "太阳·七部书（1986～1988）",
        "补遗",
    ]

    all_boundary_pages = sorted(boundaries.values())
    section_ranges = []
    for name in section_order:
        start = boundaries.get(name, 0)
        end = len(pages)
        try:
            idx_in_sorted = all_boundary_pages.index(start)
            if idx_in_sorted + 1 < len(all_boundary_pages):
                end = all_boundary_pages[idx_in_sorted + 1]
        except ValueError:
            pass
        section_ranges.append((name, start, end))

    print("\n[3/4] 解析诗歌内容...")
    all_poems = []
    for name, start, end in section_ranges:
        print(f"  处理: {name}...")
        poems = parse_poems_from_section(pages, start, end, name)
        print(f"    提取到 {len(poems)} 首")
        all_poems.extend(poems)

    print(f"\n原始提取: {len(all_poems)} 首")

    # 后处理
    print("\n[4/4] 后处理...")

    # 清理
    for poem in all_poems:
        poem["content"] = poem["content"].strip()
        poem["title"] = poem["title"].strip()

    # 过滤无效
    valid_poems = []
    for poem in all_poems:
        if len(poem["content"]) < 15:
            continue
        if not poem["title"]:
            continue
        if should_exclude_title(poem["title"]):
            continue
        if should_exclude_content(poem["content"]):
            continue
        valid_poems.append(poem)

    # 精确去重（标题+内容完全一致）
    seen = set()
    unique_poems = []
    for poem in valid_poems:
        key = poem["title"] + "|" + poem["content"][:100]
        if key not in seen:
            seen.add(key)
            unique_poems.append(poem)

    # 近似去重：同标题的诗，如果内容前30字相同则只保留较长的
    title_groups = {}
    for poem in unique_poems:
        t = poem["title"]
        if t not in title_groups:
            title_groups[t] = []
        title_groups[t].append(poem)

    final_poems = []
    for title, group in title_groups.items():
        if len(group) == 1:
            final_poems.extend(group)
        else:
            # 同标题多首：保留不同的诗，去除近似重复
            kept = [group[0]]
            for poem in group[1:]:
                is_dup = False
                for k in kept:
                    if is_near_duplicate(poem["content"], k["content"]):
                        # 保留内容更完整的
                        if len(poem["content"]) > len(k["content"]):
                            kept.remove(k)
                            kept.append(poem)
                        is_dup = True
                        break
                if not is_dup:
                    kept.append(poem)
            final_poems.extend(kept)

    print(f"过滤+去重后: {len(final_poems)} 首")

    # 按原书顺序排列（保持原有顺序，只按section分组）
    section_order_map = {name: idx for idx, name in enumerate(section_order)}
    for idx, poem in enumerate(final_poems):
        poem["_sort_idx"] = idx
    final_poems.sort(key=lambda p: (section_order_map.get(p["section"], 99), p["_sort_idx"]))
    for poem in final_poems:
        del poem["_sort_idx"]

    # 输出JSON
    output = {
        "metadata": {
            "source": "海子诗全集",
            "author": "海子",
            "editor": "西川",
            "publisher": "作家出版社",
            "description": "海子诗全集结构化数据，用于诗歌生成等NLP任务",
            "total_poems": len(final_poems),
            "sections": section_order
        },
        "poems": final_poems
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    file_size = round(len(json.dumps(output, ensure_ascii=False)) / 1024 / 1024, 2)
    print(f"\n输出文件: {OUTPUT_PATH}")
    print(f"文件大小: {file_size} MB")

    # 统计
    print("\n" + "=" * 60)
    print("统计:")
    section_counts = Counter(p["section"] for p in final_poems)
    for name in section_order:
        count = section_counts.get(name, 0)
        print(f"  {name}: {count} 首")

    no_date = sum(1 for p in final_poems if not p['date'])
    print(f"\n有日期: {len(final_poems) - no_date} 首")
    print(f"无日期: {no_date} 首")

    # 知名诗歌
    print("\n知名诗歌:")
    famous = ['亚洲铜', '面朝大海', '四姐妹', '以梦为马', '九月',
              '黑夜的献诗', '麦地', '十个海子', '五月的麦地',
              '阿尔的太阳', '新娘', '活在珍贵的人间', '祖国',
              '春天，十个海子', '日记']
    for t in famous:
        found = [p for p in final_poems if t in p['title']]
        for p in found:
            print(f"  [{p['title']}] date={p['date']} len={len(p['content'])}")

    # 同标题多首
    title_counts = Counter(p['title'] for p in final_poems)
    multi = {t: c for t, c in title_counts.items() if c > 1}
    if multi:
        print(f"\n同标题多首 ({len(multi)} 个标题):")
        for t, c in sorted(multi.items(), key=lambda x: -x[1]):
            print(f"  [{t}] x{c}")

    # 完整样例
    print("\n" + "=" * 60)
    print("样例:")
    for poem in final_poems[:2]:
        print(f"\n【{poem['title']}】")
        if poem['date']:
            print(f"日期: {poem['date']}")
        print(poem['content'])


if __name__ == "__main__":
    main()
