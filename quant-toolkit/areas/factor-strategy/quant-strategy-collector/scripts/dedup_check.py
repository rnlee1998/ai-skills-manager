#!/usr/bin/env python3
"""
Deduplication Check Script for Quant Strategy Collector

Checks a new strategy's key information against existing strategy library
documents to identify potential duplicates.

Usage:
    python dedup_check.py --library <strategy_library_path> --input <new_strategy_summary>

Arguments:
    --library: Path to the strategy library directory containing .md files
    --input: Path to a text file containing the new strategy's key information summary

Output:
    Prints a list of potentially duplicate existing documents with match scores.
"""

import sys
import argparse
from pathlib import Path

# Key terms that indicate strategy core elements
STRATEGY_KEYWORDS = [
    # Strategy types
    "趋势跟踪", "均值回归", "套利", "轮动", "多因子", "动量", "突破",
    "反转", "配对交易", "统计套利", "高频", "事件驱动", "网格交易",
    # Entry/exit signals
    "均线", "MACD", "RSI", "布林带", "ATR", "突破", "回调",
    "止损", "止盈", "信号", "入场", "出场", "金叉", "死叉",
    # ETF specific
    "ETF", "行业轮动", "宽基轮动", "风格轮动", "商品轮动",
    # Indicators
    "夏普", "回撤", "胜率", "年化", "波动率", "信息比率", "卡玛比率",
    # Markets
    "A股", "港股", "美股", "期货", "商品", "债券", "外汇",
    # Factors
    "动量因子", "价值因子", "质量因子", "波动率因子", "流动性因子",
    "资金流", "北向资金", "换手率", "成交额",
    # Position management
    "仓位管理", "等权重", "风险平价", "目标波动率",
]


def extract_keywords(text):
    """Extract strategy-related keywords from text."""
    found = []
    text_lower = text.lower()
    for kw in STRATEGY_KEYWORDS:
        if kw.lower() in text_lower:
            found.append(kw)
    return found


def extract_md_sections(filepath):
    """Extract key sections from a markdown strategy document."""
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except Exception:
        return None

    sections = {}
    current_section = "header"
    current_content = []

    for line in content.split("\n"):
        if line.startswith("## "):
            if current_content:
                sections[current_section] = "\n".join(current_content)
            current_section = line.replace("## ", "").strip()
            current_content = []
        else:
            current_content.append(line)

    if current_content:
        sections[current_section] = "\n".join(current_content)

    return sections


def extract_strategy_metadata(sections):
    """Extract key metadata from strategy sections for comparison."""
    metadata = {
        "name": "",
        "type": "",
        "market": "",
        "instrument": "",
        "tags": [],
    }

    header = sections.get("header", "")
    if header:
        for line in header.split("\n"):
            if line.startswith("# "):
                metadata["name"] = line.replace("# ", "").strip()

    background = sections.get("\u7b56\u7565\u80cc\u666f", "")
    if background:
        for line in background.split("\n"):
            if "\u7b56\u7565\u7c7b\u578b" in line:
                metadata["type"] = line.split("\uff1a")[-1].strip().strip("{}")
            if "\u9002\u7528\u5e02\u573a" in line:
                metadata["market"] = line.split("\uff1a")[-1].strip().strip("{}")
            if "\u9002\u914d\u6807\u7684" in line:
                metadata["instrument"] = line.split("\uff1a")[-1].strip().strip("{}")
            if "\u6838\u5fc3\u6807\u7b7e" in line:
                tags_text = line.split("\uff1a")[-1].strip().strip("{}")
                metadata["tags"] = [t.strip() for t in tags_text.split(",")]

    return metadata


def calculate_similarity(new_keywords, existing_keywords, new_metadata, existing_metadata):
    """Calculate similarity score between new and existing strategy."""
    # Keyword overlap score (Jaccard)
    new_set = set(new_keywords)
    existing_set = set(existing_keywords)
    if not new_set and not existing_set:
        keyword_score = 0.0
    else:
        keyword_score = len(new_set & existing_set) / max(len(new_set | existing_set), 1)

    # Metadata match score
    meta_score = 0.0
    meta_fields = ["type", "market", "instrument"]
    matches = 0
    for field in meta_fields:
        if new_metadata.get(field) and existing_metadata.get(field):
            if new_metadata[field] in existing_metadata[field] or existing_metadata[field] in new_metadata[field]:
                matches += 1
    if matches > 0:
        meta_score = matches / len(meta_fields)

    # Tag overlap score
    new_tags = set(new_metadata.get("tags", []))
    existing_tags = set(existing_metadata.get("tags", []))
    if not new_tags and not existing_tags:
        tag_score = 0.0
    else:
        tag_score = len(new_tags & existing_tags) / max(len(new_tags | existing_tags), 1)

    # Combined score (0-1 scale), weighted
    total_score = keyword_score * 0.4 + meta_score * 0.3 + tag_score * 0.3

    return total_score, keyword_score, meta_score, tag_score


def main():
    parser = argparse.ArgumentParser(
        description="Check for duplicate strategies in the strategy library"
    )
    parser.add_argument(
        "--library", required=True, help="Path to strategy library directory"
    )
    parser.add_argument(
        "--input", required=True, help="Path to new strategy summary file"
    )
    args = parser.parse_args()

    library_path = Path(args.library)
    input_path = Path(args.input)

    if not library_path.exists():
        print(f"Error: Library directory not found: {library_path}")
        sys.exit(1)

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    # Read new strategy summary
    new_content = input_path.read_text(encoding="utf-8")
    new_keywords = extract_keywords(new_content)

    print(f"New strategy keywords: {', '.join(new_keywords) if new_keywords else 'none found'}")
    print(f"Searching library: {library_path}")
    print(f"{'='*60}")

    # Scan existing library
    md_files = list(library_path.glob("*.md"))

    if not md_files:
        print("No existing strategy documents found in library.")
        print("No duplicates possible. Safe to generate new document.")
        return

    duplicates = []

    for md_file in md_files:
        existing_sections = extract_md_sections(md_file)
        if existing_sections is None:
            continue

        existing_content = "\n".join(existing_sections.values())
        existing_keywords = extract_keywords(existing_content)
        existing_metadata = extract_strategy_metadata(existing_sections)

        # For new strategy, parse as sections too if it's a full md
        new_sections = extract_md_sections(input_path)
        if new_sections:
            new_metadata = extract_strategy_metadata(new_sections)
        else:
            new_metadata = {"type": "", "market": "", "instrument": "", "tags": []}

        score, kw_score, meta_score, tag_score = calculate_similarity(
            new_keywords, existing_keywords, new_metadata, existing_metadata
        )

        strategy_name = md_file.stem

        if score > 0.15:
            duplicates.append(
                (strategy_name, score, kw_score, meta_score, tag_score, existing_keywords, md_file.name)
            )

    # Sort by score descending
    duplicates.sort(key=lambda x: x[1], reverse=True)

    if not duplicates:
        print("No potential duplicates found. Safe to generate new document.")
    else:
        print(f"Found {len(duplicates)} potentially similar document(s):")
        print(f"{'-'*60}")
        for name, score, kw, meta, tag, keywords, filename in duplicates:
            print(f"  File: {filename}")
            print(f"  Match Score: {score:.2f} (keyword: {kw:.2f}, metadata: {meta:.2f}, tags: {tag:.2f})")
            print(f"  Matched Keywords: {', '.join(keywords) if keywords else 'none'}")
            if score > 0.6:
                print(f"  >> HIGH DUPLICATION RISK - Recommend skipping")
            elif score > 0.4:
                print(f"  >> MODERATE SIMILARITY - Recommend generating with annotation")
            else:
                print(f"  >> LOW SIMILARITY - Likely safe to generate")
            print()


if __name__ == "__main__":
    main()
