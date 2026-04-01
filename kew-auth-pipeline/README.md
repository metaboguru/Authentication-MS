# Kew Botanical Extract Authentication Pipeline

A production-ready LC-MS/MS metabolomics pipeline for authenticating botanical extracts, developed for the Royal Botanic Gardens, Kew.

## Quick Start

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Install external tools (see below)

# 3. Place spectral libraries in libraries/ (GNPS, MassBank, etc.)

# 4. Run the pipeline
./scripts/run_pipeline.sh \
    data/input/sample.mzML \
    2024001 \
    "Herbal Co" \
    HC-TUR-001 \
    "Turmeric Extract" \
    "Curcuma longa" \
    Curcuma

# With an authenticated reference extract:
./scripts/run_pipeline.sh \
    data/input/sample.mzML \
    2024001 \
    "Herbal Co" \
    HC-TUR-001 \
    "Turmeric Extract" \
    "Curcuma longa" \
    Curcuma \
    data/reference/authentic_turmeric.mzML

# 5. Or use the web interface
python app.py
# Open http://localhost:7860
```

## One-Command Example

```bash
./scripts/run_pipeline.sh data/input/my_sample.mzML 2024042 "BotanCo" BC-001 "Ashwagandha Root" "Withania somnifera" Withania
```

## Required External Tools

### MZmine 3 (required for feature detection)
- Download: https://mzmine.github.io/mzmine_documentation/getting_started.html
- Add to PATH: `export PATH=$PATH:/path/to/MZmine/bin`
- Used in: Step 1 (mzML processing, ADAP chromatogram building, GNPS export)

### SIRIUS 6 (optional, for formula/fingerprint annotation)
- Download: https://bio.informatik.uni-jena.de/software/sirius/
- After install: `sirius login` (requires free academic license)
- Used in: Step 3 (molecular formula, ZODIAC, CSI:FingerID, CANOPUS)

### MS2DeepScore Model (optional, for deep learning spectral similarity)
- Download from: https://zenodo.org/records/12628369
- Place model file as: `libraries/ms2deepscore_model.pt`

### MS2Query Library (optional)
- Follow instructions at: https://github.com/iomega/ms2query
- Place library files in: `libraries/ms2query/`

### Spectral Libraries
Place `.mgf` files in the `libraries/` directory:
- **GNPS**: https://gnps.ucsd.edu/ProteoSAFe/libraries.jsp
- **MassBank**: https://massbank.eu
- **NIST**: https://chemdata.nist.gov/
- **Fiehn/Vaniya**: https://mona.fiehnlab.ucdavis.edu/

## Pipeline Steps

| Step | Script | Description |
|------|--------|-------------|
| 0 | `00_reference_handler.py` | Check for reference mzML/MGF, run direct cosine comparison |
| 1 | `01_process_mzml.py` | Validate mzML, run MZmine 3 batch processing, export MGF |
| 2 | `02_annotate_matchms.py` | Spectral matching: CosineGreedy, ModifiedCosine, MS2DeepScore |
| 3 | `03_sirius_runner.py` | SIRIUS 6: formula, ZODIAC, CSI:FingerID, CANOPUS |
| 4 | `04_literature_search.py` | PubMed, LOTUS, PubChem, HMDB verification + verdict |
| 5 | `05_generate_report.py` | Generate Kew-formatted .docx authentication report |

## Output Files

| File | Description |
|------|-------------|
| `pipeline_config.json` | Pipeline configuration (reference status, ppm, mode) |
| `reference_comparison.csv` | Reference vs query spectral comparison (if reference provided) |
| `gnps_export.mgf` | MS/MS spectra in MGF format (from MZmine) |
| `gnps_export_quant.csv` | Feature quantification table (from MZmine) |
| `merged_annotations.csv` | All spectral annotations with confidence levels |
| `sirius_annotations.csv` | SIRIUS formula/classification results |
| `literature_verification.csv` | PubMed/LOTUS/PubChem/HMDB verification results |
| `verdict.txt` | Authentication verdict and confidence |
| `Kew_Auth_Report_*.docx` | Final Kew-formatted authentication report |

## MSI Confidence Levels

- **Level 1 (Confirmed)**: Cosine >= 0.9 AND precursor m/z match within 5 ppm
- **Level 2 (Probable)**: Cosine 0.7-0.9, or SIRIUS COSMIC confidence >= 0.5
- **Level 3 (Putative)**: MS2DeepScore >= 0.5 only

## Authentication Verdicts

- **AUTHENTIC (Reference-Confirmed)**: Reference match rate >= 70%
- **AUTHENTIC (Literature-Confirmed)**: >= 70% of Level 1/2 compounds literature-confirmed
- **PROBABLE**: 40-70% confirmed
- **INCONCLUSIVE/SUSPECT**: < 40% confirmed

## Instrument Configuration

- Instrument: Thermo Orbitrap Exploris 120
- Acquisition: DDA mode
- Mass tolerance: 5 ppm throughout
- Input: mzML format (positive and/or negative polarity)

## Project Structure

```
kew-auth-pipeline/
├── .claude/agents/          # Claude Code subagent definitions
├── scripts/                 # Pipeline scripts (Steps 0-5 + runner)
├── app.py                   # Gradio web interface
├── CLAUDE.md                # Project instructions for Claude Code
├── requirements.txt         # Python dependencies
├── data/input/              # Place input mzML files here
├── data/reference/          # Place authenticated reference mzML/MGF here
├── data/output/             # Pipeline outputs
├── libraries/               # Spectral libraries (.mgf) and models
└── templates/               # Report templates
```

## Running Individual Steps

Each script can be run standalone:

```bash
python scripts/00_reference_handler.py [query_mgf] [reference_dir] [output_dir]
python scripts/01_process_mzml.py <mzml_path> [output_dir]
python scripts/02_annotate_matchms.py <query_mgf> [libraries_dir] [output_dir]
python scripts/03_sirius_runner.py <mgf_path> [output_dir]
python scripts/04_literature_search.py <output_dir> [plant_genus] [claimed_species]
python scripts/05_generate_report.py <bi_number> <manufacturer> <product_code> <commercial_name> <claimed_species> [output_dir]
```
