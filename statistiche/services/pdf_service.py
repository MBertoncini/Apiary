from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from io import BytesIO


def genera_pdf(titolo: str, colonne: list, righe: list) -> bytes:
    """Genera un file PDF formattato con i dati forniti."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    elements = []

    # Titolo
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=16,
        textColor=colors.HexColor('#1A1A2E'),
        spaceAfter=12,
    )
    elements.append(Paragraph(titolo, title_style))
    elements.append(Spacer(1, 0.4 * cm))

    if not righe:
        elements.append(Paragraph('Nessun dato disponibile.', styles['Normal']))
    else:
        # Calcola larghezza colonne
        page_width = A4[0] - 3 * cm
        n_col = len(colonne)
        col_width = page_width / n_col

        # Prepara dati tabella (header + righe)
        table_data = [colonne] + [
            [str(v) if v is not None else '' for v in row]
            for row in righe
        ]

        table = Table(table_data, colWidths=[col_width] * n_col, repeatRows=1)
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A1A2E')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, 0), 6),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            # Dati
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            # Righe alternate
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F0E8')]),
            # Griglia
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor('#D4A017')),
        ]))
        elements.append(table)

    # Footer con numero pagine
    elements.append(Spacer(1, 0.5 * cm))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
    )
    elements.append(Paragraph('Generato da Apiary Manager', footer_style))

    doc.build(elements)
    return buf.getvalue()
