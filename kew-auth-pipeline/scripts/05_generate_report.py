#!/usr/bin/env python3
"""
Step 5: Report Generation
Generates a .docx report matching the Kew Royal Botanic Gardens report format.
"""

import os
import sys
import csv
from pathlib import Path
from datetime import datetime

import pandas as pd

try:
    from docx import Document
    from docx.shared import Inches, Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.section import WD_ORIENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
except ImportError:
    print("ERROR: python-docx is required. Install with: pip install python-docx")
    sys.exit(1)


KEW_GREEN = RGBColor(0, 82, 46)  # RGB(0,82,46)
KEW_DARK = RGBColor(30, 30, 30)
KEW_GREY = RGBColor(100, 100, 100)


def set_cell_shading(cell, color_hex):
    """Set cell background shading."""
    shading = OxmlElement('w:shd')
    shading.set(qn('w:fill'), color_hex)
    shading.set(qn('w:val'), 'clear')
    cell._tc.get_or_add_tcPr().append(shading)


def set_cell_border(cell, **kwargs):
    """Set cell borders."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for edge, val in kwargs.items():
        element = OxmlElement(f'w:{edge}')
        element.set(qn('w:val'), val.get('val', 'single'))
        element.set(qn('w:sz'), val.get('sz', '4'))
        element.set(qn('w:color'), val.get('color', '000000'))
        element.set(qn('w:space'), val.get('space', '0'))
        tcBorders.append(element)
    tcPr.append(tcBorders)


def add_table_row(table, cells_data, bold=False, font_size=10, header=False):
    """Add a row to a table with formatting."""
    row = table.add_row()
    for i, text in enumerate(cells_data):
        cell = row.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        run = p.add_run(str(text))
        run.font.size = Pt(font_size)
        run.font.name = 'Calibri'
        if bold or header:
            run.bold = True
        if header:
            run.font.color.rgb = RGBColor(255, 255, 255)
            set_cell_shading(cell, '00522E')  # Kew green
    return row


def add_footer(section, bi_number):
    """Add footer to every page."""
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    run = p.add_run(
        f"Royal Botanic Gardens, Kew | Richmond, Surrey, TW9 3AE | kew.org | BI-{bi_number}"
    )
    run.font.size = Pt(8)
    run.font.color.rgb = KEW_GREY
    run.font.name = 'Calibri'


def generate_report(bi_number, manufacturer, product_code, commercial_name,
                    claimed_species, output_dir):
    """Generate the Kew authentication report."""
    print("=" * 60)
    print("STEP 5: Report Generation")
    print("=" * 60)

    output_dir = Path(output_dir)
    today = datetime.now().strftime("%d %B %Y")
    date_file = datetime.now().strftime("%Y%m%d")

    # Load data files
    annotations_path = output_dir / "merged_annotations.csv"
    literature_path = output_dir / "literature_verification.csv"
    verdict_path = output_dir / "verdict.txt"
    config_path = output_dir / "pipeline_config.json"

    ann_df = pd.DataFrame()
    if annotations_path.exists():
        ann_df = pd.read_csv(annotations_path)
        print(f"  Loaded {len(ann_df)} annotations")

    lit_df = pd.DataFrame()
    if literature_path.exists():
        lit_df = pd.read_csv(literature_path)
        print(f"  Loaded {len(lit_df)} literature verifications")

    verdict_text = "INCONCLUSIVE"
    confidence_text = ""
    if verdict_path.exists():
        with open(verdict_path) as f:
            lines = f.readlines()
        for line in lines:
            if line.startswith("Authentication Verdict:"):
                verdict_text = line.split(":", 1)[1].strip()
            elif line.startswith("Confidence:"):
                confidence_text = line.split(":", 1)[1].strip()

    has_reference = False
    if config_path.exists():
        import json
        with open(config_path) as f:
            config = json.load(f)
        has_reference = config.get('has_reference', False)

    # Filter Level 1 and 2 compounds
    l1_l2 = ann_df[ann_df['annotation_confidence_level'].isin([1, 2])].copy() if len(ann_df) > 0 else pd.DataFrame()
    l1_l2 = l1_l2.sort_values('rt') if len(l1_l2) > 0 else l1_l2

    level1 = ann_df[ann_df['annotation_confidence_level'] == 1] if len(ann_df) > 0 else pd.DataFrame()

    # Create document
    doc = Document()

    # Set default font
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(10)

    # Set margins
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)
        add_footer(section, bi_number)

    # === HEADER ===
    header_para = doc.add_paragraph()
    header_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = header_para.add_run("ROYAL BOTANIC GARDENS, KEW")
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = KEW_GREEN
    run.font.name = 'Calibri'

    # Subtitle
    sub_para = doc.add_paragraph()
    sub_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub_para.add_run("Authenticated Analysis Report")
    run.font.size = Pt(12)
    run.font.color.rgb = KEW_GREEN
    run.font.name = 'Calibri'

    # Date
    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = date_para.add_run(today)
    run.font.size = Pt(10)
    run.font.color.rgb = KEW_GREY
    run.font.name = 'Calibri'

    doc.add_paragraph()  # spacer

    # === SAMPLE INFORMATION TABLE ===
    doc.add_heading('Sample Information', level=2)

    sample_table = doc.add_table(rows=1, cols=5)
    sample_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    sample_table.style = 'Table Grid'

    headers = ['Constituents', 'Manufacturer', 'Product Code', 'Commercial Name', 'BI Number']
    header_row = sample_table.rows[0]
    for i, h in enumerate(headers):
        cell = header_row.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        run = p.add_run(h)
        run.bold = True
        run.font.size = Pt(10)
        run.font.name = 'Calibri'
        run.font.color.rgb = RGBColor(255, 255, 255)
        set_cell_shading(cell, '00522E')

    data_row = sample_table.add_row()
    data_values = [claimed_species, manufacturer, product_code, commercial_name, f"BI-{bi_number}"]
    for i, val in enumerate(data_values):
        cell = data_row.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        run = p.add_run(str(val))
        run.font.size = Pt(10)
        run.font.name = 'Calibri'

    doc.add_paragraph()

    # === SUMMARY ===
    doc.add_heading('Summary', level=2)

    total_features = len(ann_df)
    l1_count = len(ann_df[ann_df['annotation_confidence_level'] == 1]) if len(ann_df) > 0 else 0
    l2_count = len(ann_df[ann_df['annotation_confidence_level'] == 2]) if len(ann_df) > 0 else 0

    summary_text = (
        f"LC-MS/MS analysis of the botanical extract (BI-{bi_number}, claimed species: {claimed_species}) "
        f"was performed using an Orbitrap Exploris 120 in DDA mode. A total of {total_features} features "
        f"were detected, of which {l1_count} were annotated at MSI Level 1 (confirmed) and {l2_count} at "
        f"MSI Level 2 (probable). "
    )

    if has_reference:
        summary_text += "An authenticated reference extract was available for direct spectral comparison. "

    summary_text += f"The overall authentication verdict is: {verdict_text}."

    p = doc.add_paragraph(summary_text)
    p.style.font.size = Pt(10)

    doc.add_paragraph()

    # === MATERIALS & METHODS ===
    doc.add_heading('Materials & Methods', level=2)

    doc.add_heading('Sample Preparation', level=3)
    doc.add_paragraph(
        "The botanical extract was prepared according to standard Kew protocols. "
        "The sample was dissolved in methanol/water (80:20, v/v), centrifuged at 14,000 g for 10 minutes, "
        "and the supernatant was transferred to LC-MS vials for analysis."
    )

    doc.add_heading('LC-MS/MS Parameters', level=3)
    lc_params = doc.add_paragraph()
    lc_params.add_run("Instrument: ").bold = True
    lc_params.add_run("Thermo Orbitrap Exploris 120\n")
    lc_params.add_run("Acquisition mode: ").bold = True
    lc_params.add_run("Data-Dependent Acquisition (DDA)\n")
    lc_params.add_run("Column: ").bold = True
    lc_params.add_run("C18 reversed-phase (2.1 x 100 mm, 1.7 \u00b5m)\n")
    lc_params.add_run("Mobile phase A: ").bold = True
    lc_params.add_run("Water + 0.1% formic acid\n")
    lc_params.add_run("Mobile phase B: ").bold = True
    lc_params.add_run("Acetonitrile + 0.1% formic acid\n")
    lc_params.add_run("Gradient: ").bold = True
    lc_params.add_run("5-95% B over 20 min, hold 5 min, re-equilibrate 5 min\n")
    lc_params.add_run("Flow rate: ").bold = True
    lc_params.add_run("0.3 mL/min\n")
    lc_params.add_run("ESI conditions: ").bold = True
    lc_params.add_run("Spray voltage 3.5 kV, sheath gas 50, aux gas 10, capillary temp 300\u00b0C\n")
    lc_params.add_run("Mass tolerance: ").bold = True
    lc_params.add_run("5 ppm\n")
    lc_params.add_run("Resolution: ").bold = True
    lc_params.add_run("120,000 (MS1), 15,000 (MS2)")

    doc.add_heading('Data Processing', level=3)
    tools_text = (
        "Data were processed using the following tools:\n"
        "\u2022 MZmine 3 (v4.x) \u2014 feature detection, chromatogram building, GNPS/FBMN export\n"
        "\u2022 matchms (v0.18+) \u2014 spectral matching (CosineGreedy, ModifiedCosine)\n"
        "\u2022 MS2DeepScore (v0.5+) \u2014 deep learning spectral similarity\n"
        "\u2022 SIRIUS 6 \u2014 molecular formula, CSI:FingerID, CANOPUS classification\n"
        "\u2022 GNPS \u2014 spectral library matching\n"
        "\u2022 HMDB \u2014 metabolite identity confirmation\n"
        "\u2022 LOTUS \u2014 natural product-organism associations\n"
        "\u2022 PubChem \u2014 structural confirmation\n"
        "\u2022 PubMed/NCBI \u2014 literature verification\n"
        "\u2022 MetaboAnalystR \u2014 statistical analysis (where applicable)"
    )
    doc.add_paragraph(tools_text)

    doc.add_paragraph()

    # === SUMMARY OF ANALYTICAL RESULTS ===
    doc.add_heading('Summary of Analytical Results', level=2)

    findings = []
    findings.append(f"A total of {total_features} molecular features were detected by LC-MS/MS.")
    findings.append(
        f"{l1_count} compounds were confirmed at MSI Level 1 and {l2_count} at MSI Level 2."
    )
    if has_reference:
        findings.append(
            "Direct comparison with an authenticated reference extract was performed using cosine similarity."
        )

    # Add top compounds
    if len(l1_l2) > 0:
        top_compounds = l1_l2.head(3)['best_match_name'].tolist()
        top_str = ", ".join([c for c in top_compounds if c and str(c) != 'nan'])
        if top_str:
            findings.append(f"Key identified compounds include: {top_str}.")

    findings.append(f"Overall authentication verdict: {verdict_text}.")

    for i, finding in enumerate(findings[:5], 1):
        doc.add_paragraph(f"{i}. {finding}")

    doc.add_paragraph()

    # === TABLE 1: COMPOUND TABLE ===
    doc.add_heading('Table 1: Identified Compounds (MSI Level 1 & 2)', level=2)

    if len(l1_l2) > 0:
        compound_table = doc.add_table(rows=1, cols=5)
        compound_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        compound_table.style = 'Table Grid'

        ct_headers = ['Sl No', 'Molecule', 'm/z', 'Rt (min)', 'Ionisation Mode']
        ct_header_row = compound_table.rows[0]
        for i, h in enumerate(ct_headers):
            cell = ct_header_row.cells[i]
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(h)
            run.bold = True
            run.font.size = Pt(10)
            run.font.name = 'Calibri'
            run.font.color.rgb = RGBColor(255, 255, 255)
            set_cell_shading(cell, '00522E')

        for sl_no, (_, row) in enumerate(l1_l2.iterrows(), 1):
            data_row = compound_table.add_row()
            name = row.get('best_match_name', 'Unknown')
            mz_val = f"{float(row['mz']):.4f}"
            rt_val = f"{float(row['rt']):.2f}"
            ion_mode = row.get('ionisation_mode', 'unknown')

            values = [str(sl_no), str(name), mz_val, rt_val, ion_mode]
            for i, val in enumerate(values):
                cell = data_row.cells[i]
                cell.text = ""
                p = cell.paragraphs[0]
                run = p.add_run(val)
                run.font.size = Pt(9)
                run.font.name = 'Calibri'
    else:
        doc.add_paragraph("No compounds met MSI Level 1 or Level 2 confidence criteria.")

    doc.add_paragraph()

    # === FIGURES ===
    doc.add_heading('Figures', level=2)

    # Figure 1: BPC placeholder
    fig1_para = doc.add_paragraph()
    fig1_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fig1_para.add_run("[Figure 1: Base peak chromatogram of the botanical extract]")
    run.italic = True
    run.font.size = Pt(10)
    run.font.color.rgb = KEW_GREY

    bpc_path = output_dir / "bpc_chromatogram.png"
    if bpc_path.exists():
        doc.add_picture(str(bpc_path), width=Inches(5.5))

    caption1 = doc.add_paragraph()
    caption1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = caption1.add_run(
        f"Figure 1: Base peak chromatogram (BPC) of botanical extract BI-{bi_number}"
    )
    run.bold = True
    run.font.size = Pt(9)

    doc.add_paragraph()

    # Individual compound figures for Level 1
    fig_num = 2
    if len(level1) > 0:
        for _, row in level1.iterrows():
            name = row.get('best_match_name', 'Unknown')
            if not name or str(name) == 'nan':
                continue

            fig_para = doc.add_paragraph()
            fig_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = fig_para.add_run(
                f"[Figure {fig_num}: Mass spectra of {name} "
                f"(m/z {float(row['mz']):.4f}, RT {float(row['rt']):.2f} min)]"
            )
            run.italic = True
            run.font.size = Pt(10)
            run.font.color.rgb = KEW_GREY

            caption = doc.add_paragraph()
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = caption.add_run(
                f"Figure {fig_num}: MS/MS spectrum of {name} showing fragmentation pattern"
            )
            run.bold = True
            run.font.size = Pt(9)

            doc.add_paragraph()
            fig_num += 1

    # === CONCLUSION ===
    doc.add_heading('Conclusion', level=2)

    conclusion_text = (
        f"Based on the comprehensive LC-MS/MS analysis of the botanical extract "
        f"(BI-{bi_number}, {commercial_name}), the authentication verdict is: "
        f"{verdict_text}. "
    )

    if "AUTHENTIC" in verdict_text:
        conclusion_text += (
            f"The chemical profile is consistent with the claimed species ({claimed_species}). "
            f"{confidence_text}. "
            "The identified metabolites are well-documented in the scientific literature "
            "for this species."
        )
    elif "PROBABLE" in verdict_text:
        conclusion_text += (
            f"The chemical profile shows partial consistency with the claimed species ({claimed_species}). "
            f"{confidence_text}. "
            "Some key marker compounds were identified, but further analysis may be warranted."
        )
    else:
        conclusion_text += (
            f"The chemical profile could not be conclusively matched to the claimed species ({claimed_species}). "
            f"{confidence_text}. "
            "Additional analysis with authenticated reference material is recommended."
        )

    doc.add_paragraph(conclusion_text)

    doc.add_paragraph()

    # === DISCLAIMER ===
    doc.add_heading('Disclaimer', level=2)
    disclaimer_text = (
        "This report has been prepared by the Royal Botanic Gardens, Kew for the purpose of "
        "botanical extract authentication. The analysis is based on LC-MS/MS metabolite profiling "
        "and spectral library matching. Results are provided on an 'as-is' basis and should be "
        "interpreted in conjunction with other quality control measures. The Royal Botanic Gardens, "
        "Kew accepts no liability for decisions made based on this report. Metabolite annotations "
        "are assigned confidence levels following the Metabolomics Standards Initiative (MSI) "
        "guidelines. Level 1 identifications require matched retention time and MS/MS spectra "
        "against an authenticated standard. Level 2 annotations are based on spectral library "
        "matching. This report does not constitute a certificate of analysis and should not be "
        "used as the sole basis for regulatory compliance."
    )
    disclaimer_para = doc.add_paragraph(disclaimer_text)
    disclaimer_para.style.font.size = Pt(9)
    for run in disclaimer_para.runs:
        run.font.color.rgb = KEW_GREY
        run.italic = True

    doc.add_paragraph()

    # === REFERENCES ===
    doc.add_heading('References', level=2)

    if len(lit_df) > 0 and 'pubmed_ids' in lit_df.columns:
        ref_num = 1
        seen_pmids = set()
        for _, row in lit_df.iterrows():
            pmids = str(row.get('pubmed_ids', ''))
            compound = row.get('compound', '')
            if not pmids or pmids == 'nan':
                continue
            for pmid in pmids.split(';'):
                pmid = pmid.strip()
                if pmid and pmid not in seen_pmids:
                    seen_pmids.add(pmid)
                    doc.add_paragraph(
                        f"[{ref_num}] {compound}. PubMed ID: {pmid}. "
                        f"Available at: https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        style='List Number'
                    )
                    ref_num += 1
                    if ref_num > 30:
                        break
            if ref_num > 30:
                break

        if ref_num == 1:
            doc.add_paragraph("No PubMed references identified for the annotated compounds.")
    else:
        doc.add_paragraph("No literature references available.")

    # Standard references
    doc.add_paragraph()
    doc.add_paragraph(
        "Sumner, L.W. et al. (2007). Proposed minimum reporting standards for chemical analysis. "
        "Metabolomics, 3(3), 211-221.",
        style='List Number'
    )
    doc.add_paragraph(
        "Pluskal, T. et al. (2010). MZmine 2: Modular framework for processing, visualizing, "
        "and analyzing mass spectrometry-based molecular profile data. BMC Bioinformatics, 11, 395.",
        style='List Number'
    )
    doc.add_paragraph(
        "D\u00fchrkop, K. et al. (2019). SIRIUS 4: a rapid tool for turning tandem mass spectra into "
        "metabolite structure information. Nature Methods, 16, 299-302.",
        style='List Number'
    )

    # Save document
    report_filename = f"Kew_Auth_Report_{bi_number}_{date_file}.docx"
    report_path = output_dir / report_filename

    doc.save(str(report_path))
    print(f"\nReport saved: {report_path}")
    print(f"  File size: {report_path.stat().st_size} bytes")

    print("\nStep 5 complete.")
    return str(report_path)


if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("Usage: python 05_generate_report.py <bi_number> <manufacturer> <product_code> "
              "<commercial_name> <claimed_species> [output_dir]")
        sys.exit(1)

    base = Path(__file__).resolve().parent.parent
    bi = sys.argv[1]
    mfr = sys.argv[2]
    pc = sys.argv[3]
    cn = sys.argv[4]
    cs = sys.argv[5]
    out = sys.argv[6] if len(sys.argv) > 6 else str(base / "data" / "output")
    generate_report(bi, mfr, pc, cn, cs, out)
