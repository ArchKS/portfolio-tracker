#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""根据 config.json 生成买入到清仓时间线 SVG。"""

import json
import math
import os
from datetime import date
from html import escape


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")
TITLE = "买入到清仓时间线"
AS_OF_DATE = None
COLOR_BY_RETURN = True
NAME_POSITION = "left"
COLOR_SCALE_HALF = 0.6
COLORS = {
    "background": "#fbfbf8",
    "title": "#252525",
    "subtitle": "#626a73",
    "grid": "#ddd7ce",
    "line": "#2f9e67",
    "buy": "#3976af",
    "sell": "#d67b2c",
    "open": "#8b9096",
}


def parse_date(value):
    return date.fromisoformat(value) if value else None


def load_config(path=CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _lerp_color(start, end, amount):
    rgb = tuple(round(start[i] + (end[i] - start[i]) * amount) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def annualized_color(value, half):
    amount = math.tanh(value / half)
    return _lerp_color(
        (238, 232, 219),
        (196, 42, 42) if amount >= 0 else (43, 140, 84),
        abs(amount),
    )


def compute_row(trade, settings, as_of):
    buy = parse_date(trade["buy_date"])
    sell = parse_date(trade.get("sell_date"))
    row = {"name": trade["name"], "buy": buy, "sell": sell, "open": sell is None}
    if sell:
        held_years = (sell - buy).days / 365.25
        annualized = trade.get("annualized")
        if annualized is None:
            annualized = (
                (1 + trade["profit"] / trade["buy_amount"]) ** (1 / held_years) - 1
                if held_years > 0
                else 0
            )
        row["annualized"] = annualized
        row["label"] = (
            f"{held_years:.2f}年｜利润{trade['profit']}万｜年化{annualized * 100:.0f}%"
            if settings["show_amount"]
            else f"{held_years:.2f}年｜年化{annualized * 100:.0f}%"
        )
    else:
        row["end_point"] = as_of
        # status = "已回本" if trade.get("broke_even") else "未回本"
        status = "～" if trade.get("broke_even") else "-～"
        row["label"] = (
            f"未清仓｜{status}｜仓位{trade['position_pct']}%"
            if settings["show_amount"] and trade.get("position_pct") is not None
            else f"未清仓｜{status}"
        )
    return row


def legend_svg(x_left, y_top, width, height, half, text_color):
    parts = ["<g>"]
    steps = 40
    span = half * 2.2
    for index in range(steps):
        start = index / steps
        end = (index + 1) / steps
        value = -span + ((start + end) / 2) * 2 * span
        x = x_left + start * width
        parts.append(
            f'<rect x="{x:.2f}" y="{y_top}" width="{(end - start) * width:.2f}" '
            f'height="{height}" fill="{annualized_color(value, half)}"/>'
        )
    for tick in (-100, -50, 0, 50, 100, 150):
        value = tick / 100
        if -span <= value <= span:
            x = x_left + (value + span) / (2 * span) * width
            parts.append(
                f'<line x1="{x:.2f}" y1="{y_top}" x2="{x:.2f}" y2="{y_top + height}" '
                'stroke="#fff" stroke-width="1" opacity=".6"/>'
            )
            parts.append(
                f'<text x="{x:.2f}" y="{y_top + height + 16}" font-size="11" '
                f'fill="{text_color}" text-anchor="middle">{tick}%</text>'
            )
    parts.append(
        f'<text x="{x_left}" y="{y_top - 6}" font-size="11" '
        f'fill="{text_color}">年化收益率</text></g>'
    )
    return "".join(parts)


def build_svg(config):
    settings = config.get("timeline", {})
    trades = settings.get("trades", [])
    if not trades:
        return ""
    as_of = parse_date(AS_OF_DATE) or date.today()
    rows = [compute_row(trade, settings, as_of) for trade in trades]
    colors = COLORS
    layout = settings["layout"]
    name_position = NAME_POSITION
    plot_start = (
        layout["plot_x_start_left"]
        if name_position == "left"
        else layout["plot_x_start_bar_center"]
    )
    plot_end = layout["plot_x_end"]

    all_dates = []
    for row in rows:
        all_dates.extend([row["buy"], row["sell"] or row["end_point"]])
    min_year = min(value.year for value in all_dates)
    max_year = max(value.year for value in all_dates) + 1
    date_start = date(min_year, 1, 1)
    date_end = date(max_year, 1, 1)
    pixels_per_day = (plot_end - plot_start) / (date_end - date_start).days

    def x_of(value):
        return plot_start + (value - date_start).days * pixels_per_day

    height = layout["row_start_y"] + layout["row_height"] * len(rows) + 70
    width = plot_end + 220
    title = escape(TITLE)
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{title}">',
        f'<rect width="100%" height="100%" fill="{colors["background"]}"/>',
        '<style>text{font-family:"Inter","Noto Sans SC","PingFang SC",'
        '"Microsoft YaHei",Arial,sans-serif;}</style>',
        f'<text x="{layout["left_margin"]}" y="58" font-size="28" font-weight="700" '
        f'fill="{colors["title"]}">{title}</text>',
    ]
    if COLOR_BY_RETURN:
        subtitle = (
            f"蓝点：买入；橙点：清仓；灰线：未清仓，截至 {as_of.isoformat()}；"
            "柱色：年化收益率（红高绿低）。"
        )
        svg.append(
            legend_svg(
                width - 260,
                40,
                220,
                12,
                COLOR_SCALE_HALF,
                colors["subtitle"],
            )
        )
    else:
        subtitle = f"蓝点：买入；橙点：清仓；灰线：未清仓，截至 {as_of.isoformat()}。"
    svg.append(
        f'<text x="{layout["left_margin"]}" y="88" font-size="15" '
        f'fill="{colors["subtitle"]}">{escape(subtitle)}</text>'
    )

    for year in range(min_year, max_year + 1):
        x = x_of(date(year, 1, 1))
        svg.extend(
            [
                f'<line x1="{x:.2f}" y1="115" x2="{x:.2f}" y2="{height - 45}" '
                f'stroke="{colors["grid"]}" opacity=".65" stroke-dasharray="3 5"/>',
                f'<text x="{x:.2f}" y="{height - 20}" font-size="13" '
                f'fill="{colors["subtitle"]}" text-anchor="middle">{year}</text>',
            ]
        )

    row_y = layout["row_start_y"]
    for row in rows:
        if name_position == "left":
            svg.append(
                f'<text x="{layout["left_margin"]}" y="{row_y + 5}" font-size="16" '
                f'font-weight="700" fill="{colors["title"]}">{escape(row["name"])}</text>'
            )
        x_buy = x_of(row["buy"])
        x_end = x_of(row["sell"] or row["end_point"])
        if row["open"]:
            svg.extend(
                [
                    f'<line x1="{x_buy:.2f}" y1="{row_y}" x2="{x_end:.2f}" y2="{row_y}" '
                    f'stroke="{colors["open"]}" stroke-width="9" opacity=".9"/>',
                    f'<polygon points="{x_end:.2f},{row_y - 8} {x_end - 7.6:.2f},{row_y + 6} '
                    f'{x_end + 7.6:.2f},{row_y + 6}" fill="{colors["open"]}" '
                    'stroke="#fff" stroke-width="2"/>',
                ]
            )
        else:
            bar_color = (
                annualized_color(row["annualized"], COLOR_SCALE_HALF)
                if COLOR_BY_RETURN
                else colors["line"]
            )
            svg.extend(
                [
                    f'<line x1="{x_buy:.2f}" y1="{row_y}" x2="{x_end:.2f}" y2="{row_y}" '
                    f'stroke="{bar_color}" stroke-width="9" opacity=".95"/>',
                    f'<circle cx="{x_end:.2f}" cy="{row_y}" r="8" fill="{colors["sell"]}" '
                    'stroke="#fff" stroke-width="2"/>',
                ]
            )
        svg.append(
            f'<circle cx="{x_buy:.2f}" cy="{row_y}" r="8" fill="{colors["buy"]}" '
            'stroke="#fff" stroke-width="2"/>'
        )
        if name_position == "bar_center":
            svg.append(
                f'<text x="{(x_buy + x_end) / 2:.2f}" y="{row_y - 14}" font-size="15" '
                f'font-weight="700" fill="{colors["title"]}" text-anchor="middle">'
                f'{escape(row["name"])}</text>'
            )
        label_x = min(x_end + layout["right_label_pad"], width - 260)
        svg.append(
            f'<text x="{label_x:.2f}" y="{row_y + 5}" font-size="14" '
            f'fill="{colors["subtitle"]}">{escape(row["label"])}</text>'
        )
        row_y += layout["row_height"]
    svg.append("</svg>")
    return "\n".join(svg)


def generate_timeline_svg(config=None, write_file=True):
    config = config or load_config()
    svg = build_svg(config)
    if svg and write_file:
        filename = os.path.basename(config["timeline"].get("output_file", "timeline.svg"))
        with open(os.path.join(PROJECT_DIR, filename), "w", encoding="utf-8") as file:
            file.write(svg)
    return svg


def main():
    config = load_config()
    svg = generate_timeline_svg(config)
    if not svg:
        raise SystemExit("config.json 中没有配置 timeline.trades")
    print(f"[OK] 已生成: {config['timeline'].get('output_file', 'timeline.svg')}")


if __name__ == "__main__":
    main()
