#!/usr/bin/env python3
"""将通用性格调查问卷 Markdown 转换为 PDF（使用 fpdf2）"""

import re
from pathlib import Path
from fpdf import FPDF

MD_PATH = Path(__file__).parent.parent / "questionnaires" / "通用性格调查问卷.md"
PDF_PATH = Path(__file__).parent.parent / "questionnaires" / "通用性格调查问卷.pdf"

# ── 字体路径 ───────────────────────────────────────────────────
FONT_DIR = Path("/System/Library/Fonts")
FONT_HEITI = FONT_DIR / "STHeiti Medium.ttc"
FONT_SONGTI = FONT_DIR / "Supplemental" / "Songti.ttc"

# ── 解析 Markdown ──────────────────────────────────────────────

md_text = MD_PATH.read_text(encoding="utf-8")
lines = md_text.split("\n")

# 结构: list of (type, content)
# type: "h1", "h2", "h3", "p", "note", "hr", "score_table", "item"
elements: list[tuple[str, object]] = []
current_items: list[dict] = []


def flush_items():
    if current_items:
        elements.append(("items", current_items.copy()))
        current_items.clear()


for line in lines:
    s = line.strip()

    if s.startswith("# ") and not s.startswith("## "):
        flush_items()
        elements.append(("h1", s[2:]))
    elif s.startswith("## ") and not s.startswith("### "):
        flush_items()
        elements.append(("h2", s[3:]))
    elif s.startswith("### "):
        flush_items()
        elements.append(("h3", s[4:]))
    elif s == "---":
        flush_items()
        elements.append(("hr", ""))
    elif s.startswith("|") and "---" not in s and "分数" not in s:
        cells = [c.strip() for c in s.split("|")[1:-1]]
        if len(cells) == 2:
            elements.append(("score_table", cells))
    elif s.startswith("本问卷") or s.startswith("请根据"):
        flush_items()
        elements.append(("p", s))
    elif s.startswith("注意：") or s.startswith("- "):
        flush_items()
        elements.append(("note", s))
    elif m := re.match(r"\*\*(\d+)\.\*\*\s*(.*)", s):
        num = int(m.group(1))
        text = m.group(2).strip()
        is_rev = "*(R)*" in text
        text = text.replace("*(R)*", "").strip()
        current_items.append({"no": num, "text": text, "rev": is_rev})
    elif re.match(r"^`[1-5]`\s+`[1-5]`", s):
        pass  # 选项行，已在 item 中处理
    elif not s:
        pass
    else:
        flush_items()
        elements.append(("p", s))

flush_items()


# ── PDF 生成 ────────────────────────────────────────────────────

class QuestionnairePDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        # 注册字体
        self.add_font("heiti", "", str(FONT_HEITI), uni=True)
        self.add_font("songti", "", str(FONT_SONGTI), uni=True)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(15, 15, 15)

    def header(self):
        pass  # 不需要页眉

    def footer(self):
        self.set_y(-12)
        self.set_font("songti", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"{self.page_no()} / {{nb}}", align="C")

    def add_h1(self, text):
        self.set_font("heiti", "", 18)
        self.set_text_color(30, 30, 30)
        self.cell(0, 14, text, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def add_h2(self, text):
        self.ln(6)
        self.set_font("heiti", "", 14)
        self.set_text_color(26, 82, 118)
        self.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT")
        # 下划线
        y = self.get_y()
        self.set_draw_color(26, 82, 118)
        self.set_line_width(0.5)
        self.line(15, y, 195, y)
        self.ln(3)

    def add_h3(self, text):
        self.ln(3)
        self.set_font("heiti", "", 11)
        self.set_text_color(46, 134, 193)
        self.cell(0, 8, f"  {text}", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def add_p(self, text):
        self.set_font("songti", "", 10)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 6, text)
        self.ln(2)

    def add_note(self, text):
        self.set_font("songti", "", 9)
        self.set_text_color(100, 100, 100)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def add_hr(self):
        self.ln(3)
        y = self.get_y()
        self.set_draw_color(200, 200, 200)
        self.set_line_width(0.3)
        self.line(15, y, 195, y)
        self.ln(3)

    def add_score_table(self, cells):
        self.set_font("songti", "", 10)
        self.set_text_color(50, 50, 50)
        w1, w2 = 25, 50
        x = 15
        self.set_x(x)
        self.cell(w1, 7, cells[0], border=1, align="C")
        self.cell(w2, 7, cells[1], border=1)
        self.ln()

    def add_items(self, items):
        """渲染一组题目，每题: 编号 | 题目文字 | 1 2 3 4 5"""
        # 列宽
        col_no = 10      # 编号
        col_opts = 46     # 选项
        col_text = 180 - col_no - col_opts  # 剩余给文字

        for it in items:
            # 检查是否需要换页（预估行高）
            est_lines = max(1, len(it["text"]) / 28 + 1)  # 粗估
            est_h = est_lines * 6 + 4
            if self.get_y() + est_h > 280:
                self.add_page()

            no_str = f"{it['no']}."
            y0 = self.get_y()
            x0 = 15

            # 编号
            self.set_font("heiti", "", 10)
            self.set_text_color(100, 100, 100)
            self.set_xy(x0, y0)
            self.cell(col_no, 6, no_str, align="R")

            # 题目文字
            self.set_font("songti", "", 10)
            self.set_text_color(40, 40, 40)
            text_x = x0 + col_no + 2
            self.set_xy(text_x, y0)
            self.multi_cell(col_text, 6, it["text"])
            y_after_text = self.get_y()

            # R 标记
            if it["rev"]:
                self.set_font("heiti", "", 7)
                self.set_text_color(231, 76, 60)
                rev_x = text_x + self.get_string_width(it["text"]) + 2
                if rev_x + 8 < text_x + col_text:
                    self.set_xy(rev_x, y0)
                    self.cell(8, 6, "R", align="L")

            # 选项 1-5
            opts_x = x0 + col_no + col_text + 2
            self.set_font("songti", "", 9)
            self.set_text_color(120, 120, 120)
            # 居中于文字区域的右侧
            for i, v in enumerate(["1", "2", "3", "4", "5"]):
                cx = opts_x + i * 9
                cy = y0
                self.set_xy(cx, cy)
                # 画圆圈
                self.set_draw_color(160, 160, 160)
                self.set_line_width(0.3)
                r = 3.5
                self.ellipse(cx, cy + 0.5, r * 2, r * 2)
                self.set_xy(cx, cy + 0.5)
                self.cell(r * 2, r * 2, v, align="C")

            # 移到下一行
            self.set_y(max(y_after_text, y0 + 8))
            self.ln(1.5)


# ── 构建 PDF ────────────────────────────────────────────────────

pdf = QuestionnairePDF()
pdf.alias_nb_pages()
pdf.add_page()

for etype, content in elements:
    if etype == "h1":
        pdf.add_h1(content)
    elif etype == "h2":
        pdf.add_h2(content)
    elif etype == "h3":
        pdf.add_h3(content)
    elif etype == "p":
        pdf.add_p(content)
    elif etype == "note":
        pdf.add_note(content)
    elif etype == "hr":
        pdf.add_hr()
    elif etype == "score_table":
        pdf.add_score_table(content)
    elif etype == "items":
        pdf.add_items(content)

pdf.output(str(PDF_PATH))
print(f"✅ 已生成: {PDF_PATH}")
