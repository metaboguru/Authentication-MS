# Kew Botanical Extract Authentication Pipeline

## Overview
This pipeline authenticates botanical extracts using LC-MS/MS metabolomics data. It is designed for the Royal Botanic Gardens, Kew authentication research programme.

## Instrument Configuration
- **Acquisition mode**: DDA (Data-Dependent Acquisition)
- **Instrument**: Thermo Orbitrap Exploris 120
- **Mass tolerance**: 5 ppm throughout all processing steps
- **Input format**: mzML (converted from .raw via MSConvert or ThermoRawFileParser)
- **Polarity**: Positive and/or Negative ESI

## Pipeline Steps

### Step 0 — Reference Handler (`scripts/00_reference_handler.py`)
Checks `data/reference/` for an authentic reference mzML or MGF file. If present, this becomes the **HIGHEST PRIORITY** comparison source. The pipeline performs direct CosineGreedy spectral matching (tolerance = mz * 5/1e6 Da, dynamic ppm-to-Da conversion) and PrecursorMzMatch (5 ppm) between query and reference spectra. Features are flagged as MATCH (cosine >= 0.9), PARTIAL_MATCH (>= 0.7), WEAK_MATCH (>= 0.4), or NO_MATCH (< 0.4). If no reference file exists, the pipeline falls back to spectral libraries + literature only.

### Step 1 — mzML Processing (`scripts/01_process_mzml.py`)
Validates the mzML file using pyopenms (MS1/MS2 scan counts, polarity, RT range). Generates and executes a MZmine 3 batch XML for Orbitrap DDA data with ADAP chromatogram builder, minimum search resolver, GroupMS2, and GNPS/FBMN export. Outputs: `gnps_export.mgf` and `gnps_export_quant.csv`.

### Step 2 — Spectral Annotation (`scripts/02_annotate_matchms.py`)
Loads the query MGF and all available spectral libraries (GNPS, MassBank, NIST, Fiehn/Vaniya) from `libraries/`. Runs CosineGreedy, ModifiedCosine, PrecursorMzMatch, and optionally MS2DeepScore and MS2Query. Merges all scores into `merged_annotations.csv`. If a reference comparison exists, merges and upgrades confidence for matched features.

### Step 3 — SIRIUS Annotation (`scripts/03_sirius_runner.py`)
Runs SIRIUS 6 CLI for molecular formula prediction, ZODIAC, CSI:FingerID, and CANOPUS classification. Outputs `sirius_annotations.csv`. Skips gracefully if SIRIUS is not installed.

### Step 4 — Literature Search (`scripts/04_literature_search.py`)
Queries PubMed, LOTUS, PubChem, and HMDB for Level 1 and Level 2 compounds. Calculates authentication verdict based on reference match rate and literature confirmation rate. Outputs `literature_verification.csv` and `verdict.txt`.

### Step 5 — Report Generation (`scripts/05_generate_report.py`)
Generates a .docx report matching the Kew report format: letterhead, sample table, compound table, MS spectra figure placeholders, conclusion, disclaimer, and references. Output: `data/output/Kew_Auth_Report_{bi_number}_{date}.docx`.

## MSI Confidence Levels
- **Level 1 (Confirmed)**: Cosine >= 0.9 AND precursor m/z match within 5 ppm — or reference MATCH flag
- **Level 2 (Probable)**: Cosine 0.7–0.9, or SIRIUS COSMIC confidence >= 0.5
- **Level 3 (Putative)**: MS2DeepScore >= 0.5 only, no spectral library match

## Critical Rules
- **Never fabricate compound annotations** — only report matches above threshold with real scores
- **Report ALL plant species detected** — no cap on number of species or compounds
- **5 ppm tolerance** everywhere — use dynamic ppm-to-Da conversion: `tolerance_da = mz * 5.0 / 1e6`
- **Reference mzML is optional** — check `pipeline_config.json` at each step
- Output must match the Kew report format exactly
