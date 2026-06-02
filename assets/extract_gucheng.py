#!/usr/bin/env python3
"""Extract poems from 顾城诗全编 PDF and convert to JSON.

Uses font size and x-position from PyMuPDF to identify:
- Titles (size ~15.8, centered)
- Body text (size ~12.1, left-aligned)
- Dates (size ~10.5, right-aligned)
- Page headers/footers (size ~10.5, top/bottom)
- Year dividers (size ~21.0, centered)
"""

import json
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import fitz

PDF_PATH = r'c:\Users\tianmacheng\Desktop\test\PoemGenerator\[顾城诗全编].顾城.文字版.pdf'
OUTPUT_PATH = r'c:\Users\tianmacheng\Desktop\test\PoemGenerator\gucheng_poems.json'

# Poem pages range (1-indexed)
POEM_START_PAGE = 46
POEM_END_PAGE = 1025


def extract_page_chars(page):
    """Extract character-level data from a page with position and size info."""
    blocks = page.get_text('dict')['blocks']
    chars = []
    for block in blocks:
        if 'lines' in block:
            for line in block['lines']:
                for span in line['spans']:
                    text = span['text']
                    bbox = span['bbox']
                    size = span['size']
                    if text.strip():
                        chars.append({
                            'x0': bbox[0], 'y0': bbox[1],
                            'x1': bbox[2], 'y1': bbox[3],
                            'text': text.strip(), 'size': size
                        })
    return chars


def reconstruct_lines(chars):
    """Group characters into lines based on y-coordinate proximity."""
    if not chars:
        return []

    chars.sort(key=lambda c: (round(c['y0']), c['x0']))

    lines = []
    current_line = []
    current_y = None

    for ch in chars:
        y = round(ch['y0'])
        if current_y is None or abs(y - current_y) > 3:
            if current_line:
                lines.append(current_line)
            current_line = [ch]
            current_y = y
        else:
            current_line.append(ch)

    if current_line:
        lines.append(current_line)

    result = []
    for line_chars in lines:
        line_chars.sort(key=lambda c: c['x0'])

        # Dominant size
        sizes = [c['size'] for c in line_chars]
        dominant_size = max(set(sizes), key=sizes.count)

        # Average x0
        avg_x = sum(c['x0'] for c in line_chars) / len(line_chars)

        # Build text with spaces based on x-gaps
        parts = []
        for i, ch in enumerate(line_chars):
            if i == 0:
                parts.append(ch['text'])
            else:
                prev = line_chars[i - 1]
                gap = ch['x0'] - (prev['x0'] + len(prev['text']) * 6)
                if gap > 8:
                    parts.append(' ' + ch['text'])
                else:
                    parts.append(ch['text'])

        text = ''.join(parts)

        # Classify line type by font size and position
        if dominant_size >= 18:
            line_type = 'year_divider'
        elif dominant_size >= 14:
            line_type = 'title'
        elif dominant_size <= 11.5 and avg_x > 250:
            line_type = 'date'
        elif dominant_size <= 11.5 and avg_x < 120:
            line_type = 'header_footer'
        elif dominant_size >= 11 and dominant_size <= 13:
            line_type = 'body'
        else:
            line_type = 'other'

        result.append({
            'text': text,
            'type': line_type,
            'size': dominant_size,
            'x0': line_chars[0]['x0'],
            'avg_x': avg_x,
        })

    return result


def fullwidth_to_halfwidth(text):
    """Convert fullwidth digits and punctuation to halfwidth."""
    result = text
    for fw, hw in zip('０１２３４５６７８９○〇', '012345678900'):
        result = result.replace(fw, hw)
    return result


def is_page_header(text):
    """Check if text is a page header like 'N 顾城诗全编'."""
    text = text.strip()
    return '顾城诗全编' in text


def clean_title(title):
    """Remove extra spaces from poem titles, keeping spaces only where needed."""
    # Remove spaces between Chinese characters
    # Pattern: Chinese char + space(s) + Chinese char -> remove spaces
    cleaned = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', title)
    # Repeat to handle multiple spaces
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', cleaned)
    # Clean up remaining multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def clean_date(date_str):
    """Clean and validate a date string. Returns (date, subtitle)."""
    if not date_str:
        return "", ""
    date_str = re.sub(r'\s+', '', date_str)
    # Check if it looks like a date (contains year pattern)
    if re.match(r'^[0-9]{4}年', date_str):
        return date_str, ""
    # It's likely a subtitle/epigraph (e.g., "——我想在大地上画满窗子...")
    return "", date_str


def extract_all_poems():
    """Main extraction logic."""
    doc = fitz.open(PDF_PATH)
    print(f"PDF has {doc.page_count} pages")

    all_lines = []
    current_year = ""

    for page_idx in range(POEM_START_PAGE - 1, min(POEM_END_PAGE - 1, doc.page_count)):
        page_num = page_idx + 1
        chars = extract_page_chars(doc[page_idx])
        lines = reconstruct_lines(chars)

        for line in lines:
            text = fullwidth_to_halfwidth(line['text'].strip())
            line_type = line['type']

            if is_page_header(text):
                continue

            if line_type == 'year_divider':
                year_match = re.search(r'[0-9]{4}', text.replace(' ', ''))
                if year_match:
                    current_year = year_match.group()
                else:
                    cn = text.replace(' ', '').replace('年', '')
                    cn_num = cn
                    for cn_ch, digit in zip('一二三四五六七八九零', '1234567890'):
                        cn_num = cn_num.replace(cn_ch, digit)
                    cn_num = cn_num.replace('○', '0').replace('〇', '0')
                    if len(cn_num) == 4 and cn_num.isdigit():
                        current_year = cn_num
                continue

            if line_type == 'header_footer':
                continue

            if not text:
                continue

            all_lines.append({
                'text': text,
                'type': line_type,
                'page': page_num,
                'year': current_year,
            })

    doc.close()
    print(f"Extracted {len(all_lines)} content lines")

    # Parse poems from the line stream
    poems = []
    i = 0

    while i < len(all_lines):
        line = all_lines[i]
        text = line['text']
        line_type = line['type']

        # Skip date/subtitle lines at top level
        if line_type == 'date':
            i += 1
            continue

        # Only process title lines
        if line_type != 'title':
            i += 1
            continue

        # Found a title
        title = clean_title(text)
        poem_year = line.get('year', '')

        # Collect body content until next title
        content_lines = []
        date = ""
        subtitle = ""
        i += 1

        while i < len(all_lines):
            cline = all_lines[i]
            ctext = cline['text']
            ctype = cline['type']

            if ctype == 'title':
                break

            if ctype == 'date':
                # Could be a date or a subtitle/epigraph
                d, sub = clean_date(ctext.strip())
                if d:
                    date = d
                if sub:
                    subtitle = sub
                i += 1
                continue

            if ctype in ('body', 'other'):
                content_lines.append(ctext.strip())
                i += 1
                continue

            i += 1

        # Build content string
        content = '\n'.join(content_lines).strip()
        content = re.sub(r'\n{3,}', '\n\n', content)

        # Prepend subtitle if present
        if subtitle:
            content = subtitle + '\n' + content

        if content and len(content) >= 2:
            poems.append({
                'title': title,
                'content': content,
                'date': date,
                'section': poem_year if poem_year else "",
            })

    return poems


def main():
    print("Extracting poems from 顾城诗全编...")
    poems = extract_all_poems()
    print(f"\nFound {len(poems)} poems")

    # Stats
    sections = []
    section_counts = {}
    for p in poems:
        s = p['section']
        if s not in section_counts:
            sections.append(s)
        section_counts[s] = section_counts.get(s, 0) + 1

    for s in sections:
        print(f"  {s}: {section_counts[s]} poems")

    # Save
    output = {
        'metadata': {
            'source': '顾城诗全编',
            'author': '顾城',
            'total_poems': len(poems),
            'sections': sections,
        },
        'poems': poems,
    }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to {OUTPUT_PATH}")

    # Print sample poems
    print("\n=== Sample poems ===")
    for p in poems[:5]:
        print(f"\n【{p['title']}】({p['date']}) [{p['section']}]")
        print(p['content'][:100])


if __name__ == '__main__':
    main()
