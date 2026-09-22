"""Geração de anexo JPG por central a partir das ocorrências sincronizadas."""
from __future__ import annotations

from datetime import date
import calendar
from io import BytesIO
from pathlib import Path
import textwrap

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


NAVY = "#315A9B"
GREEN = "#00A66A"
AMBER = "#F5A600"
RED = "#D91F35"
GRAY = "#9AA8B8"
GRID = "#9DA9B7"
PALE_BLUE = "#E8EEF7"
WHITE = "#FFFFFF"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")
    for name in names:
        for directory in (Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")):
            path = directory / name
            if path.exists():
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _value(value: object, empty: str = "—") -> str:
    return empty if value is None or pd.isna(value) or str(value).strip() == "" else str(value)


def _operational_dates(frame: pd.DataFrame) -> pd.Series:
    starts = frame["Data/hora de início"] if "Data/hora de início" in frame else pd.Series(index=frame.index, dtype=object)
    due = frame["Data/hora limite"] if "Data/hora limite" in frame else pd.Series(index=frame.index, dtype=object)
    return pd.to_datetime(starts.fillna(due), errors="coerce", utc=True)


def _report_due_date(row: pd.Series) -> pd.Timestamp:
    """Obtém o vencimento apresentado pelo SafetyCulture para a ocorrência."""
    for field in ("Data/hora de fim", "Data/hora limite"):
        value = row.get(field)
        timestamp = pd.to_datetime(value, errors="coerce", utc=True)
        if not pd.isna(timestamp):
            return timestamp
    return pd.NaT


def _monthly_deadline(row: pd.Series, reference_month: date) -> pd.Timestamp:
    """Mantém o prazo da atividade dentro do mês a que o relatório se refere."""
    due_date = _report_due_date(row)
    last_day = calendar.monthrange(reference_month.year, reference_month.month)[1]
    month_end = pd.Timestamp(date(reference_month.year, reference_month.month, last_day), tz="UTC")
    if pd.isna(due_date) or due_date > month_end:
        return month_end
    return due_date


def _belongs_to_local(value: object, local: str) -> bool:
    return local in {part.strip() for part in str(value or "").split(",")}


def _wrapped_lines(text: object, width: int) -> list[str]:
    """Divide o nome completo em linhas, sem perder conteúdo."""
    return textwrap.wrap(_value(text, "Sem atividade"), width=width) or ["Sem atividade"]


def _draw_wrapped(draw: ImageDraw.ImageDraw, position: tuple[int, int], text: object, font: ImageFont.ImageFont, fill: str, width: int) -> None:
    """Desenha o texto completo em linhas curtas, sem o cortar."""
    lines = _wrapped_lines(text, width)
    x, y = position
    line_height = int(font.size * 1.15) if hasattr(font, "size") else 18
    for index, line in enumerate(lines):
        draw.text((x, y + index * line_height), line, font=font, fill=fill)


def report_locations(frame: pd.DataFrame) -> list[str]:
    names: set[str] = set()
    for value in frame.get("Local", pd.Series(dtype=object)).dropna():
        names.update(part.strip() for part in str(value).split(",") if part.strip())
    return sorted(names)


def report_months(frame: pd.DataFrame) -> list[date]:
    timestamps = _operational_dates(frame).dropna()
    return sorted({date(value.year, value.month, 1) for value in timestamps})


def create_central_report_jpg(frame: pd.DataFrame, local: str, reference_month: date) -> bytes:
    """Cria uma página JPG com o mês e o planeamento até dezembro."""
    source = frame[frame["Local"].map(lambda value: _belongs_to_local(value, local))].copy()
    source["_date"] = _operational_dates(source)
    monthly = source[
        (source["_date"].dt.year == reference_month.year)
        & (source["_date"].dt.month == reference_month.month)
    ].copy()
    end_of_year = pd.Timestamp(date(reference_month.year, 12, 31), tz="UTC")
    planning = source[(source["_date"] >= pd.Timestamp(reference_month, tz="UTC")) & (source["_date"] <= end_of_year)].copy()

    # O relatório cresce conforme necessário. Assim, nenhum nome de atividade
    # é encurtado e nenhuma linha é descartada por falta de espaço.
    monthly_rows = list(monthly.sort_values("_date").iterrows())
    planning_rows = list(planning.sort_values("_date").iterrows())
    activity_font = _font(18)
    activity_line_height = int(activity_font.size * 1.15) if hasattr(activity_font, "size") else 18
    monthly_row_heights = [max(86, len(_wrapped_lines(row.get("Atividade"), 42)) * activity_line_height + 26) for _, row in monthly_rows]
    timeline_row_heights = [max(95, len(_wrapped_lines(row.get("Atividade"), 31)) * activity_line_height + 28) for _, row in planning_rows]
    table_top = 770
    table_bottom = table_top + 125 + sum(monthly_row_heights) + 25
    timeline_top = table_bottom + 40
    timeline_bottom = timeline_top + 165 + sum(timeline_row_heights) + 35

    image = Image.new("RGB", (1600, timeline_bottom + 75), WHITE)
    draw = ImageDraw.Draw(image)
    title_font, body_font, small_font = _font(31, True), _font(26), _font(20)
    metric_font, table_font = _font(58, True), _font(24)

    def rectangle(box: tuple[int, int, int, int], fill: str = WHITE, outline: str = GRID, width: int = 2) -> None:
        draw.rectangle(box, fill=fill, outline=outline, width=width)

    statuses = monthly["Estado"].fillna("")
    counts = {
        "Previstas": len(monthly),
        "Concluídas": int(statuses.isin(["Concluído", "Concluído com atraso"]).sum()),
        "Em andamento": int((statuses == "Em andamento").sum()),
        "Disponíveis": int((statuses == "Disponível").sum()),
    }
    x_positions = [55, 435, 815, 1195]
    for x, (label, value) in zip(x_positions, counts.items()):
        rectangle((x, 55, x + 350, 230), outline="#1E1E1E")
        draw.rectangle((x, 55, x + 350, 115), fill=NAVY)
        draw.text((x + 20, 67), label.upper(), font=small_font, fill=WHITE)
        color = GREEN if label == "Concluídas" else AMBER if label == "Em andamento" else NAVY
        draw.text((x + 28, 135), str(value), font=metric_font, fill=color)

    # Estado das atividades e resumo do período.
    rectangle((55, 270, 930, 730), outline="#1E1E1E")
    draw.rectangle((55, 270, 930, 335), fill=NAVY)
    draw.text((80, 283), "ESTADO DAS ATIVIDADES", font=title_font, fill=WHITE)
    pie_box = (100, 375, 450, 675)
    pie_parts = [("Concluídas", counts["Concluídas"], GREEN), ("Em andamento", counts["Em andamento"], AMBER), ("Disponíveis", counts["Disponíveis"], GRAY)]
    total_for_pie = max(sum(value for _, value, _ in pie_parts), 1)
    start_angle = -90
    for _, value, color in pie_parts:
        extent = 360 * value / total_for_pie
        draw.pieslice(pie_box, start_angle, start_angle + extent, fill=color, outline=WHITE)
        start_angle += extent
    draw.ellipse((195, 470, 355, 630), fill=WHITE)
    draw.text((235, 510), str(len(monthly)), font=_font(42, True), fill=NAVY)
    draw.text((222, 560), "atividades", font=small_font, fill=NAVY)
    for index, (label, value, color) in enumerate(pie_parts):
        y = 415 + index * 85
        draw.ellipse((525, y, 550, y + 25), fill=color)
        draw.text((570, y - 3), label, font=body_font, fill=NAVY)
        draw.text((850, y - 3), str(value), font=body_font, fill=NAVY, anchor="ra")
        draw.line((520, y + 45, 875, y + 45), fill="#D2D9E2", width=2)

    rectangle((960, 270, 1545, 730), outline="#1E1E1E")
    draw.rectangle((960, 270, 1545, 335), fill=NAVY)
    draw.text((985, 283), "RESUMO DO PERÍODO", font=title_font, fill=WHITE)
    for index, (label, value) in enumerate(counts.items()):
        y = 390 + index * 75
        draw.text((1000, y), label, font=body_font, fill=NAVY)
        draw.text((1500, y), str(value), font=body_font, fill=NAVY, anchor="ra")
        draw.line((995, y + 48, 1515, y + 48), fill="#D2D9E2", width=2)

    # Planeamento mensal.
    rectangle((55, table_top, 1545, table_bottom), outline="#1E1E1E")
    draw.rectangle((55, table_top, 1545, table_top + 65), fill=NAVY)
    draw.text((80, table_top + 13), "PLANEAMENTO MENSAL", font=title_font, fill=WHITE)
    headers = [(55, 545, "ATIVIDADE"), (545, 950, "ESTADO"), (950, 1195, "PRAZO"), (1195, 1545, "DATA DE CONCLUSÃO")]
    for left, right, label in headers:
        draw.rectangle((left, table_top + 65, right, table_top + 125), fill=NAVY, outline="#1E1E1E")
        draw.text((left + 18, table_top + 80), label, font=small_font, fill=WHITE)
    if not monthly_rows:
        draw.text((80, table_top + 165), "Sem atividades sincronizadas para este mês.", font=body_font, fill=NAVY)
    monthly_y = table_top + 125
    for (_, row), monthly_row_height in zip(monthly_rows, monthly_row_heights):
        y = monthly_y
        draw.line((55, y + monthly_row_height, 1545, y + monthly_row_height), fill=GRID, width=1)
        for x in (545, 950, 1195):
            draw.line((x, y, x, y + monthly_row_height), fill=GRID, width=1)
        status = _value(row.get("Estado"))
        status_color = GREEN if status.startswith("Concluído") else AMBER if status == "Em andamento" else RED if status in ("Em atraso", "Não concluído") else GRAY
        _draw_wrapped(draw, (78, y + 13), row.get("Atividade"), activity_font, NAVY, 42)
        draw.ellipse((575, y + 30, 595, y + 50), fill=status_color)
        draw.text((610, y + 26), status, font=table_font, fill=NAVY)
        due_date = _monthly_deadline(row, reference_month)
        due_label = due_date.strftime("%d/%m/%Y")
        draw.text((970, y + 26), due_label, font=table_font, fill=NAVY)
        completed = pd.to_datetime(row.get("Concluído em"), errors="coerce", utc=True)
        completed_label = "—" if pd.isna(completed) else completed.strftime("%d/%m/%Y")
        draw.text((1215, y + 26), completed_label, font=table_font, fill=NAVY)
        monthly_y += monthly_row_height

    # Planeamento trimestral: mês de referência até dezembro.
    rectangle((55, timeline_top, 1545, timeline_bottom), outline="#1E1E1E")
    draw.rectangle((55, timeline_top, 1545, timeline_top + 65), fill=NAVY)
    draw.text((80, timeline_top + 13), "PLANEAMENTO TRIMESTRAL", font=title_font, fill=WHITE)
    months = [date(reference_month.year, month, 1) for month in range(reference_month.month, 13)]
    months = months[:3]
    label_width, timeline_left, timeline_right = 420, 475, 1515
    month_width = (timeline_right - timeline_left) / max(len(months), 1)
    for index, month in enumerate(months):
        left = int(timeline_left + index * month_width)
        right = int(timeline_left + (index + 1) * month_width)
        draw.rectangle((left, timeline_top + 85, right, timeline_top + 145), fill=PALE_BLUE, outline=GRID)
        draw.text(((left + right) // 2, timeline_top + 102), month.strftime("%B").upper(), font=small_font, fill=NAVY, anchor="ma")
    timeline_y = timeline_top + 165
    for (_, row), timeline_row_height in zip(planning_rows, timeline_row_heights):
        y = timeline_y
        _draw_wrapped(draw, (80, y + 12), row.get("Atividade"), activity_font, NAVY, 31)
        draw.line((55, y + timeline_row_height, timeline_right, y + timeline_row_height), fill=GRID, width=1)
        date_value = row["_date"]
        month_index = max(0, min(len(months) - 1, date_value.month - reference_month.month))
        left = int(timeline_left + month_index * month_width + 30)
        right = min(int(left + month_width * 0.72), timeline_right - 10)
        status = _value(row.get("Estado"))
        color = GREEN if status.startswith("Concluído") else AMBER if status == "Em andamento" else GRAY
        draw.rounded_rectangle((left, y + 33, right, y + 61), radius=6, fill=color)
        timeline_y += timeline_row_height

    output = BytesIO()
    image.save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()
