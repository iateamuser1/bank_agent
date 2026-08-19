"""Generate a simple but valid PDF bank statement on the fly."""

from __future__ import annotations

from fpdf import FPDF


def statement_pdf(bank_name: str, account_holder: str, period: str, rows: list[tuple[str, str, str]]) -> bytes:
    """Return the bytes of a one-page PDF statement.

    rows: list of (date, description, amount)."""
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, bank_name, ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, "Account Statement", ln=True)
    pdf.ln(2)
    pdf.cell(0, 7, f"Account holder: {account_holder}", ln=True)
    pdf.cell(0, 7, f"Statement period: {period}", ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(35, 8, "Date", border=1)
    pdf.cell(110, 8, "Description", border=1)
    pdf.cell(40, 8, "Amount", border=1, ln=True)

    pdf.set_font("Helvetica", "", 10)
    for date, desc, amount in rows:
        pdf.cell(35, 8, date, border=1)
        pdf.cell(110, 8, desc, border=1)
        pdf.cell(40, 8, amount, border=1, ln=True)

    out = pdf.output()               # fpdf2 returns a bytearray
    return bytes(out)
