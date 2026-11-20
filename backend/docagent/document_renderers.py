"""Render the same structured narrative to Markdown, Word and PDF."""

import re
from pathlib import Path
from xml.sax.saxutils import escape


def contents_sections(sections):
    # Individual test records are navigable by their headings without filling
    # the opening pages with a second copy of the case catalogue.
    entries, seen = [], set()
    for index, (heading, bodies) in enumerate(sections):
        records = [body["table"] for body in bodies if isinstance(body, dict) and
                   body.get("table", {}).get("headers") == ["Field", "Test specification"]]
        if records:
            requirement = records[0]["rows"][1][1].split(" (REQ-")[0]
            if requirement not in seen:
                entries.append((index, requirement + " scenarios"))
                seen.add(requirement)
        else:
            entries.append((index, heading))
    return entries


def markdown(title, metadata, sections):
    lines = [f"# {title}", "", metadata, ""]
    lines.extend(["## Contents", ""])
    for _, heading in contents_sections(sections):
        anchor = re.sub(r"[^\w -]", "", heading.lower()).replace(" ", "-")
        lines.append(f"- [{heading}](#{anchor})")
    lines.append("")
    for heading, bodies in sections:
        lines.extend([f"## {heading}", ""])
        for body in bodies:
            if isinstance(body, str):
                lines.extend([body, ""])
            elif "table" in body:
                data = body["table"]

                def cell(value):
                    return str(value).replace("|", r"\|").replace("\n", "<br>")

                lines.append("| " + " | ".join(map(cell, data["headers"])) + " |")
                lines.append("| " + " | ".join("---" for _ in data["headers"]) + " |")
                lines.extend("| " + " | ".join(map(cell, row)) + " |" for row in data["rows"])
                lines.append("")
            elif "list" in body:
                lines.extend(f"- {item}" for item in body["list"])
                lines.append("")
            elif "image" in body:
                lines.extend([f"![{body['caption']}]({body['image']})", "", body["caption"], ""])
    return "\n".join(lines)


def write_docx(path, title, metadata, sections):
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    document = Document()
    page = document.sections[0]
    page.top_margin = page.bottom_margin = Inches(0.7)
    page.left_margin = page.right_margin = Inches(0.8)
    for name, size in (("Normal", 11), ("Title", 25), ("Heading 1", 15), ("Heading 2", 12)):
        style = document.styles[name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.space_after = Pt(7)
        style.paragraph_format.space_before = Pt(12 if name.startswith("Heading") else 0)
    document.styles["Normal"].paragraph_format.line_spacing = 1.12
    document.add_paragraph(title, "Title")
    document.add_paragraph(metadata)
    entries = contents_sections(sections)
    if len(entries) > 6:
        document.add_heading("Contents", level=1)
        for index, heading in entries:
            p = document.add_paragraph()
            link = OxmlElement("w:hyperlink")
            link.set(qn("w:anchor"), f"section_{index}")
            run = OxmlElement("w:r")
            text = OxmlElement("w:t")
            text.text = heading
            run.append(text)
            link.append(run)
            p._p.append(link)

    def add_table(data):
        tbl = document.add_table(rows=1, cols=len(data["headers"]))
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        available = page.page_width - page.left_margin - page.right_margin
        # Record specifications and summary tables need a compact label column.
        fractions = [0.25, 0.75] if len(data["headers"]) == 2 else (
            [0.25, 0.48, 0.27] if len(data["headers"]) == 3 else [0.2, 0.2, 0.35, 0.25]
        )
        for column, fraction in zip(tbl.columns, fractions):
            column.width = int(available * fraction)
        for index, value in enumerate(data["headers"]):
            tbl.rows[0].cells[index].text = str(value)
        repeat = OxmlElement("w:tblHeader")
        tbl.rows[0]._tr.get_or_add_trPr().append(repeat)
        for values in data["rows"]:
            row = tbl.add_row()
            for cell, value in zip(row.cells, values):
                cell.text = str(value)
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            tag = OxmlElement(f"w:{edge}")
            for key, value in (("val", "single"), ("sz", "4"), ("color", "D9D9D9")):
                tag.set(qn(f"w:{key}"), value)
            borders.append(tag)
        tbl._tbl.tblPr.append(borders)
        for row_index, row in enumerate(tbl.rows):
            for cell_index, cell in enumerate(row.cells):
                cell.width = int(available * fractions[cell_index])
                props = cell._tc.get_or_add_tcPr()
                margins = OxmlElement("w:tcMar")
                for edge in ("top", "left", "bottom", "right"):
                    item = OxmlElement(f"w:{edge}")
                    item.set(qn("w:w"), "90")
                    item.set(qn("w:type"), "dxa")
                    margins.append(item)
                props.append(margins)
                shading = OxmlElement("w:shd")
                shading.set(qn("w:fill"), "243449" if row_index == 0 else "F3F6F8" if row_index % 2 else "FFFFFF")
                props.append(shading)
                for p in cell.paragraphs:
                    p.paragraph_format.space_after = Pt(3)
                    p.paragraph_format.line_spacing = 1.05
                    if data["headers"] == ["Field", "Test specification"]:
                        p.paragraph_format.keep_with_next = row_index < len(tbl.rows) - 1
                    for run in p.runs:
                        run.font.size = Pt(10)
                        if row_index == 0:
                            run.bold = True
                            run.font.color.rgb = RGBColor(255, 255, 255)
        document.add_paragraph().paragraph_format.space_after = Pt(2)

    for index, (heading, bodies) in enumerate(sections):
        p = document.add_heading(heading, level=1)
        bookmark = OxmlElement("w:bookmarkStart")
        bookmark.set(qn("w:id"), str(index))
        bookmark.set(qn("w:name"), f"section_{index}")
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), str(index))
        p._p.insert(0, bookmark)
        p._p.append(end)
        for body in bodies:
            if isinstance(body, str):
                document.add_paragraph(body)
            elif "table" in body:
                add_table(body["table"])
            elif "list" in body:
                for item in body["list"]:
                    p = document.add_paragraph("\u2022 " + item)
                    p.paragraph_format.left_indent = Pt(12)
                    p.paragraph_format.first_line_indent = Pt(-9)
            elif "image" in body:
                image_path = Path(path).parent / body["image"]
                if image_path.is_file():
                    from PIL import Image

                    with Image.open(image_path) as image:
                        width, height = image.size
                    scale = min(6.6 / width, 6.7 / height)
                    p = document.add_paragraph()
                    p.paragraph_format.keep_with_next = True
                    p.add_run().add_picture(str(image_path), width=Inches(width * scale))
                    document.add_paragraph(body["caption"], style="Caption")
    footer = page.footer.paragraphs[0]
    footer.add_run("Evidence based draft | Review required | Page ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    document.core_properties.title = title
    document.core_properties.author = "Repository Documentation Agent"
    for element in (document._element, document.styles.element):
        for border in element.xpath(".//w:pBdr"):
            border.getparent().remove(border)
    document.save(path)


def write_pdf(path, title, metadata, sections):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Image,
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    styles = getSampleStyleSheet()
    for name in ("Title", "Heading1", "Heading2"):
        styles[name].textColor = colors.black
        styles[name].keepWithNext = True
    styles.add(ParagraphStyle("BodyWrap", fontName="Helvetica", fontSize=10, leading=14,
                              spaceAfter=8, splitLongWords=True))
    styles.add(ParagraphStyle("Cell", fontName="Helvetica", fontSize=8.5, leading=11))
    styles.add(ParagraphStyle("HeaderCell", parent=styles["Cell"], textColor=colors.white))

    def para(text, style="BodyWrap"):
        safe = escape(str(text).encode("cp1252", errors="replace").decode("cp1252")).replace("\n", "<br/>")
        return Paragraph(safe, styles[style])

    story = [para(title, "Title"), para(metadata), Spacer(1, 12)]
    for heading, bodies in sections:
        section_start = len(story)
        story.append(para(heading, "Heading1"))
        for body in bodies:
            if isinstance(body, str):
                story.append(para(body))
            elif "table" in body:
                data = body["table"]
                values = [[para(v, "HeaderCell") for v in data["headers"]]]
                values.extend([para(v, "Cell") for v in row] for row in data["rows"])
                ratios = [0.25, 0.75] if len(data["headers"]) == 2 else (
                    [0.25, 0.48, 0.27] if len(data["headers"]) == 3 else [0.2, 0.2, 0.35, 0.25]
                )
                tbl = Table(values, colWidths=[6.9 * inch * value for value in ratios], repeatRows=1, hAlign="LEFT")
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243449")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6F8")]),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9D9D9")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.extend([tbl, Spacer(1, 9)])
            elif "list" in body:
                story.extend(para("- " + item) for item in body["list"])
            elif "image" in body:
                image_path = Path(path).parent / body["image"]
                if image_path.is_file():
                    picture = Image(str(image_path))
                    scale = min(6.7 * inch / picture.imageWidth, 6.5 * inch / picture.imageHeight)
                    picture.drawWidth = picture.imageWidth * scale
                    picture.drawHeight = picture.imageHeight * scale
                    story.extend([picture, para(body["caption"])])
        keep_record = any(isinstance(body, dict) and body.get("table", {}).get("headers") == ["Field", "Test specification"] for body in bodies)
        keep_short_prose = all(isinstance(body, str) for body in bodies) and sum(len(body) for body in bodies) < 1800
        if keep_record or keep_short_prose:
            story[section_start:] = [KeepTogether(story[section_start:])]

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.drawString(0.7 * inch, 0.4 * inch, "Evidence based draft | Review required")
        canvas.drawRightString(7.6 * inch, 0.4 * inch, str(doc.page))

    SimpleDocTemplate(str(path), rightMargin=0.7 * inch, leftMargin=0.7 * inch,
                      topMargin=0.7 * inch, bottomMargin=0.7 * inch, title=title).build(
                          story, onFirstPage=footer, onLaterPages=footer)
