#!/usr/bin/env python3
"""
Kew Botanical Extract Authentication Pipeline — Gradio Web Interface
Royal Botanic Gardens, Kew
"""

import os
import sys
import subprocess
import threading
import json
from pathlib import Path
from datetime import datetime

import gradio as gr
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR / "scripts"
OUTPUT_DIR = BASE_DIR / "data" / "output"
REFERENCE_DIR = BASE_DIR / "data" / "reference"
INPUT_DIR = BASE_DIR / "data" / "input"
LIBRARIES_DIR = BASE_DIR / "libraries"

KEW_GREEN = "#00522E"
KEW_LIGHT = "#E8F5E9"

# Custom CSS for Kew green theme
CUSTOM_CSS = """
.gradio-container {
    max-width: 1200px !important;
}
.kew-header {
    text-align: center;
    color: #00522E;
    font-weight: bold;
    font-size: 24px;
    margin-bottom: 5px;
}
.kew-subtitle {
    text-align: center;
    color: #00522E;
    font-size: 14px;
    margin-bottom: 20px;
}
.verdict-authentic {
    background-color: #C8E6C9 !important;
    color: #1B5E20 !important;
    font-size: 18px !important;
    font-weight: bold !important;
    padding: 15px !important;
    border-radius: 8px !important;
    text-align: center !important;
}
.verdict-probable {
    background-color: #FFF3E0 !important;
    color: #E65100 !important;
    font-size: 18px !important;
    font-weight: bold !important;
    padding: 15px !important;
    border-radius: 8px !important;
    text-align: center !important;
}
.verdict-inconclusive {
    background-color: #FFCDD2 !important;
    color: #B71C1C !important;
    font-size: 18px !important;
    font-weight: bold !important;
    padding: 15px !important;
    border-radius: 8px !important;
    text-align: center !important;
}
.confidence-info {
    padding: 10px;
    border-radius: 5px;
    margin-top: 10px;
    font-size: 13px;
}
"""


def run_pipeline_step(cmd, step_name, log_lines):
    """Run a pipeline step and capture output."""
    log_lines.append(f"\n{'='*50}")
    log_lines.append(f"[{datetime.now().strftime('%H:%M:%S')}] {step_name}")
    log_lines.append(f"{'='*50}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(BASE_DIR)
        )

        for line in process.stdout:
            line = line.rstrip()
            log_lines.append(line)

        process.wait()

        if process.returncode != 0:
            log_lines.append(f"WARNING: {step_name} exited with code {process.returncode}")
            return False
        return True

    except Exception as e:
        log_lines.append(f"ERROR in {step_name}: {str(e)}")
        return False


def run_full_pipeline(mzml_file, ref_file, bi_number, manufacturer,
                      product_code, commercial_name, claimed_species,
                      plant_genus, polarity, progress=gr.Progress()):
    """Run the complete authentication pipeline."""
    log_lines = []
    log_lines.append("ROYAL BOTANIC GARDENS, KEW")
    log_lines.append("Botanical Extract Authentication Pipeline")
    log_lines.append(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_lines.append("")

    # Validate inputs
    if not mzml_file:
        return ("ERROR: Please upload an mzML file.", None,
                "No input file provided.", None, None)

    if not bi_number:
        bi_number = datetime.now().strftime("%Y%m%d")

    # Copy input file
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    import shutil
    mzml_path = INPUT_DIR / Path(mzml_file).name
    shutil.copy2(mzml_file, str(mzml_path))
    log_lines.append(f"Input file: {mzml_path}")

    # Copy reference if provided
    if ref_file:
        ref_path = REFERENCE_DIR / Path(ref_file).name
        shutil.copy2(ref_file, str(ref_path))
        log_lines.append(f"Reference file: {ref_path}")

    python = sys.executable

    # STEP 0: Reference Handler
    progress(0.05, desc="Step 0: Reference Handler")
    run_pipeline_step(
        [python, str(SCRIPTS_DIR / "00_reference_handler.py"), "", str(REFERENCE_DIR), str(OUTPUT_DIR)],
        "STEP 0: Reference Handler",
        log_lines
    )

    # STEP 1: mzML Processing
    progress(0.15, desc="Step 1: mzML Processing")
    success = run_pipeline_step(
        [python, str(SCRIPTS_DIR / "01_process_mzml.py"), str(mzml_path), str(OUTPUT_DIR)],
        "STEP 1: mzML Processing (MZmine 3)",
        log_lines
    )

    mgf_path = OUTPUT_DIR / "gnps_export.mgf"

    if not success or not mgf_path.exists():
        log_lines.append("")
        log_lines.append("Step 1 failed — MZmine 3 may not be installed.")
        log_lines.append("Install MZmine 3 from https://mzmine.github.io")
        log_lines.append("")
        log_lines.append("Continuing with remaining steps if MGF exists...")

    # Re-run Step 0 with MGF if reference exists
    config_path = OUTPUT_DIR / "pipeline_config.json"
    if config_path.exists() and mgf_path.exists():
        with open(config_path) as f:
            config = json.load(f)
        if config.get('has_reference', False):
            progress(0.20, desc="Step 0: Reference comparison")
            run_pipeline_step(
                [python, str(SCRIPTS_DIR / "00_reference_handler.py"),
                 str(mgf_path), str(REFERENCE_DIR), str(OUTPUT_DIR)],
                "STEP 0 (re-run): Reference comparison with query MGF",
                log_lines
            )

    # STEP 2: Spectral Annotation
    if mgf_path.exists():
        progress(0.35, desc="Step 2: Spectral Annotation")
        run_pipeline_step(
            [python, str(SCRIPTS_DIR / "02_annotate_matchms.py"),
             str(mgf_path), str(LIBRARIES_DIR), str(OUTPUT_DIR)],
            "STEP 2: Spectral Annotation (matchms)",
            log_lines
        )

    # STEP 3: SIRIUS
    if mgf_path.exists():
        progress(0.55, desc="Step 3: SIRIUS Annotation")
        run_pipeline_step(
            [python, str(SCRIPTS_DIR / "03_sirius_runner.py"),
             str(mgf_path), str(OUTPUT_DIR)],
            "STEP 3: SIRIUS Annotation",
            log_lines
        )

    # STEP 4: Literature Search
    progress(0.75, desc="Step 4: Literature Search")
    run_pipeline_step(
        [python, str(SCRIPTS_DIR / "04_literature_search.py"),
         str(OUTPUT_DIR), plant_genus or "", claimed_species or ""],
        "STEP 4: Literature Search & Verification",
        log_lines
    )

    # STEP 5: Report Generation
    progress(0.90, desc="Step 5: Report Generation")
    run_pipeline_step(
        [python, str(SCRIPTS_DIR / "05_generate_report.py"),
         bi_number, manufacturer or "Unknown", product_code or "N/A",
         commercial_name or "Unknown", claimed_species or "Unknown", str(OUTPUT_DIR)],
        "STEP 5: Report Generation",
        log_lines
    )

    progress(1.0, desc="Complete")
    log_lines.append("")
    log_lines.append(f"Pipeline completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Read results
    log_text = "\n".join(log_lines)

    # Read compound table
    compounds_df = None
    ann_path = OUTPUT_DIR / "merged_annotations.csv"
    if ann_path.exists():
        try:
            df = pd.read_csv(ann_path)
            display_cols = ['feature_id', 'best_match_name', 'mz', 'rt',
                            'ionisation_mode', 'cosine_score', 'annotation_confidence_level']
            available_cols = [c for c in display_cols if c in df.columns]
            compounds_df = df[available_cols].head(15)
        except Exception:
            pass

    # Read verdict
    verdict_text = "Pipeline completed — check log for details."
    verdict_path = OUTPUT_DIR / "verdict.txt"
    if verdict_path.exists():
        with open(verdict_path) as f:
            verdict_text = f.read()

    # Find output files
    csv_file = str(ann_path) if ann_path.exists() else None
    report_files = list(OUTPUT_DIR.glob("Kew_Auth_Report_*.docx"))
    docx_file = str(report_files[0]) if report_files else None

    return log_text, compounds_df, verdict_text, csv_file, docx_file


def create_app():
    """Create the Gradio interface."""

    with gr.Blocks(
        title="Kew Authentication Pipeline",
    ) as app:

        gr.HTML("""
        <div class="kew-header">ROYAL BOTANIC GARDENS, KEW</div>
        <div class="kew-subtitle">Botanical Extract Authentication Pipeline</div>
        """)

        with gr.Row():
            # Left panel — inputs
            with gr.Column(scale=1):
                gr.Markdown("### Input Files")

                mzml_input = gr.File(
                    label="mzML File (required)",
                    file_types=[".mzML", ".mzml"],
                    type="filepath"
                )

                ref_input = gr.File(
                    label="Reference mzML/MGF (optional — highest priority comparison)",
                    file_types=[".mzML", ".mzml", ".mgf", ".MGF"],
                    type="filepath"
                )

                gr.Markdown("### Sample Information")

                bi_number = gr.Textbox(label="BI Number", placeholder="e.g., 2024001")
                manufacturer = gr.Textbox(label="Manufacturer", placeholder="e.g., Herbal Co Ltd")
                product_code = gr.Textbox(label="Product Code", placeholder="e.g., HC-TUR-001")
                commercial_name = gr.Textbox(label="Commercial Name", placeholder="e.g., Turmeric Extract")
                claimed_species = gr.Textbox(label="Claimed Species", placeholder="e.g., Curcuma longa")
                plant_genus = gr.Textbox(label="Plant Genus", placeholder="e.g., Curcuma")

                polarity = gr.Radio(
                    choices=["positive", "negative", "both"],
                    label="Polarity",
                    value="positive"
                )

                run_btn = gr.Button(
                    "Run Authentication Pipeline",
                    variant="primary",
                    size="lg"
                )

            # Right panel — results
            with gr.Column(scale=2):
                gr.Markdown("### Pipeline Log")
                log_output = gr.Textbox(
                    label="Processing Log",
                    lines=18,
                    max_lines=30,
                    interactive=False,
                )

                gr.Markdown("### Compound Results (Top 15 by Cosine Score)")
                results_table = gr.Dataframe(
                    label="Annotated Compounds",
                    interactive=False,
                    wrap=True
                )

                gr.Markdown("### Authentication Verdict")
                verdict_output = gr.Textbox(
                    label="Verdict",
                    lines=5,
                    interactive=False
                )

        # Bottom — downloads
        with gr.Row():
            csv_download = gr.File(label="Download Annotation CSV", interactive=False)
            docx_download = gr.File(label="Download Kew Report (.docx)", interactive=False)

        # Info panel
        with gr.Accordion("MSI Confidence Levels", open=False):
            gr.Markdown("""
### Metabolomics Standards Initiative (MSI) Confidence Levels

| Level | Name | Criteria | Colour |
|-------|------|----------|--------|
| **Level 1** | Confirmed | Cosine >= 0.9 AND precursor m/z match (5 ppm), or reference MATCH | Green |
| **Level 2** | Probable | Cosine 0.7-0.9, or SIRIUS COSMIC confidence >= 0.5 | Orange |
| **Level 3** | Putative | MS2DeepScore >= 0.5 only, no spectral library match | Red |

**Reference matching** (when an authenticated reference extract is provided):
- **MATCH**: Cosine >= 0.9 (upgrades to Level 1)
- **PARTIAL_MATCH**: Cosine >= 0.7 (upgrades to Level 2)
- **WEAK_MATCH**: Cosine >= 0.4
- **NO_MATCH**: Cosine < 0.4

**Authentication verdict**:
- **AUTHENTIC (Reference-Confirmed)**: Reference match rate >= 70%
- **AUTHENTIC (Literature-Confirmed)**: Library + literature confirmed >= 70% of Level 1/2 compounds
- **PROBABLE**: 40-70% confirmed
- **INCONCLUSIVE/SUSPECT**: < 40% confirmed
            """)

        with gr.Accordion("Pipeline Information", open=False):
            gr.Markdown("""
### Pipeline Steps

1. **Step 0 — Reference Handler**: Checks for authenticated reference mzML/MGF. Runs direct cosine comparison if available.
2. **Step 1 — mzML Processing**: Validates and processes mzML via MZmine 3 (ADAP builder, resolver, GNPS export).
3. **Step 2 — Spectral Annotation**: matchms CosineGreedy, ModifiedCosine, PrecursorMzMatch, MS2DeepScore, MS2Query.
4. **Step 3 — SIRIUS Annotation**: Molecular formula, ZODIAC, CSI:FingerID, CANOPUS classification.
5. **Step 4 — Literature Search**: PubMed, LOTUS, PubChem, HMDB verification. Calculates authentication verdict.
6. **Step 5 — Report Generation**: Kew-formatted .docx report with sample table, compound table, figures, conclusion.

### Required Tools
- **MZmine 3**: https://mzmine.github.io (feature detection)
- **SIRIUS 6**: https://bio.informatik.uni-jena.de/software/sirius/ (optional, formula/fingerprint)
- **Spectral libraries**: Place .mgf files in `libraries/` directory
            """)

        # Wire up the run button
        run_btn.click(
            fn=run_full_pipeline,
            inputs=[mzml_input, ref_input, bi_number, manufacturer,
                    product_code, commercial_name, claimed_species,
                    plant_genus, polarity],
            outputs=[log_output, results_table, verdict_output,
                     csv_download, docx_download],
            show_progress="full"
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        css=CUSTOM_CSS,
        theme=gr.themes.Soft(
            primary_hue=gr.themes.colors.green,
            secondary_hue=gr.themes.colors.emerald,
        ),
    )
