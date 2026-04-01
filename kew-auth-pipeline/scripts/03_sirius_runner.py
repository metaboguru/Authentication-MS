#!/usr/bin/env python3
"""
Step 3: SIRIUS 6 Runner
Runs SIRIUS CLI for molecular formula, ZODIAC, CSI:FingerID, and CANOPUS.
Parses output summaries into sirius_annotations.csv.
"""

import os
import sys
import subprocess
import shutil
import csv
from pathlib import Path


def check_sirius_installed():
    """Check if SIRIUS CLI is available."""
    sirius_cmd = shutil.which("sirius")
    if sirius_cmd:
        try:
            result = subprocess.run([sirius_cmd, "--version"], capture_output=True, text=True, timeout=30)
            version = result.stdout.strip() or result.stderr.strip()
            print(f"  SIRIUS found: {version}")
            return sirius_cmd
        except Exception:
            return sirius_cmd
    return None


def run_sirius(mgf_path, output_dir, sirius_cmd):
    """Run the full SIRIUS pipeline."""
    sirius_out = Path(output_dir) / "sirius_out"
    sirius_out.mkdir(parents=True, exist_ok=True)

    cmd = [
        sirius_cmd,
        "--input", str(mgf_path),
        "--output", str(sirius_out),
        "--no-compression",
        "formula",
        "--profile", "orbitrap",
        "--ppm-max", "5",
        "--ppm-max-ms2", "10",
        "--candidates", "10",
        "--db", "BIO",
        "--ions-considered", "[M+H]+,[M+Na]+,[M-H]-,[M+Cl]-",
        "zodiac",
        "fingerid",
        "--db", "BIO",
        "canopus",
        "write-summaries",
        "--output", str(sirius_out / "summaries"),
    ]

    print(f"  Running: {' '.join(cmd[:10])}...")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200  # 2 hour timeout
        )
        if result.returncode != 0:
            print(f"  SIRIUS STDERR (last 1000 chars):\n{result.stderr[-1000:]}")
            print(f"  SIRIUS exited with code {result.returncode}")
            if "login" in result.stderr.lower() or "license" in result.stderr.lower():
                print("\n  NOTE: SIRIUS requires login. Run: sirius login")
            return False
        print("  SIRIUS pipeline completed successfully.")
        return True
    except subprocess.TimeoutExpired:
        print("ERROR: SIRIUS timed out after 2 hours.")
        return False
    except Exception as e:
        print(f"ERROR running SIRIUS: {e}")
        return False


def parse_formula_identifications(summaries_dir):
    """Parse formula_identifications.tsv from SIRIUS summaries."""
    tsv_path = Path(summaries_dir) / "formula_identifications.tsv"
    if not tsv_path.exists():
        # Try alternative paths
        for alt in ["formula_identifications.tsv", "compound_identifications.tsv"]:
            alt_path = Path(summaries_dir) / alt
            if alt_path.exists():
                tsv_path = alt_path
                break
        else:
            print(f"  WARNING: No formula identifications found in {summaries_dir}")
            return {}

    results = {}
    with open(tsv_path, 'r') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            fid = row.get('id') or row.get('featureId') or row.get('mappingFeatureId', '')
            results[fid] = {
                'sirius_formula': row.get('molecularFormula', ''),
                'adduct': row.get('adduct', ''),
                'precursorMz': row.get('precursorFormula', row.get('ionMass', '')),
                'sirius_compound_name': row.get('name', ''),
                'smiles': row.get('smiles', ''),
                'inchikey': row.get('InChIkey', row.get('inchikey', '')),
            }
    print(f"  Parsed {len(results)} formula identifications")
    return results


def parse_canopus_summary(summaries_dir):
    """Parse canopus_compound_summary.tsv from SIRIUS summaries."""
    tsv_path = Path(summaries_dir) / "canopus_compound_summary.tsv"
    if not tsv_path.exists():
        for alt in ["canopus_summary.tsv", "canopus_compound_classifications.tsv"]:
            alt_path = Path(summaries_dir) / alt
            if alt_path.exists():
                tsv_path = alt_path
                break
        else:
            print(f"  WARNING: No CANOPUS summary found in {summaries_dir}")
            return {}

    results = {}
    with open(tsv_path, 'r') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            fid = row.get('id') or row.get('featureId') or row.get('mappingFeatureId', '')
            results[fid] = {
                'npc_pathway': row.get('NPC#pathway', row.get('npc_pathway', '')),
                'npc_superclass': row.get('NPC#superclass', row.get('npc_superclass', '')),
                'npc_class': row.get('NPC#class', row.get('npc_class', '')),
                'sirius_cosmic_confidence': row.get('ConfidenceScore',
                    row.get('confidenceScore', row.get('cosmic_confidence', ''))),
            }
    print(f"  Parsed {len(results)} CANOPUS classifications")
    return results


def merge_sirius_results(formula_results, canopus_results, output_path):
    """Merge formula and CANOPUS results into sirius_annotations.csv."""
    all_ids = set(list(formula_results.keys()) + list(canopus_results.keys()))

    rows = []
    for fid in sorted(all_ids):
        formula = formula_results.get(fid, {})
        canopus = canopus_results.get(fid, {})

        rows.append({
            'id': fid,
            'sirius_formula': formula.get('sirius_formula', ''),
            'adduct': formula.get('adduct', ''),
            'precursorMz': formula.get('precursorMz', ''),
            'sirius_compound_name': formula.get('sirius_compound_name', ''),
            'sirius_cosmic_confidence': canopus.get('sirius_cosmic_confidence', ''),
            'npc_pathway': canopus.get('npc_pathway', ''),
            'npc_superclass': canopus.get('npc_superclass', ''),
            'npc_class': canopus.get('npc_class', ''),
            'smiles': formula.get('smiles', ''),
            'inchikey': formula.get('inchikey', ''),
        })

    fieldnames = ['id', 'sirius_formula', 'adduct', 'precursorMz',
                  'sirius_compound_name', 'sirius_cosmic_confidence',
                  'npc_pathway', 'npc_superclass', 'npc_class',
                  'smiles', 'inchikey']

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Wrote sirius_annotations.csv ({len(rows)} compounds)")
    return rows


def run_sirius_pipeline(mgf_path, output_dir):
    """Main SIRIUS pipeline."""
    print("=" * 60)
    print("STEP 3: SIRIUS Annotation")
    print("=" * 60)

    mgf_path = Path(mgf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not mgf_path.exists():
        print(f"ERROR: MGF file not found: {mgf_path}")
        sys.exit(1)

    sirius_cmd = check_sirius_installed()
    if not sirius_cmd:
        print("\n" + "=" * 60)
        print("WARNING: SIRIUS 6 is not installed or not in PATH.")
        print("")
        print("Install SIRIUS 6:")
        print("  1. Download from https://bio.informatik.uni-jena.de/software/sirius/")
        print("     or https://github.com/boecker-lab/sirius")
        print("  2. Extract and add to PATH")
        print("  3. Run: sirius login")
        print("     (requires free academic or commercial license)")
        print("")
        print("Skipping SIRIUS annotation — pipeline continues without it.")
        print("=" * 60)

        # Write empty sirius_annotations.csv
        output_csv = output_dir / "sirius_annotations.csv"
        fieldnames = ['id', 'sirius_formula', 'adduct', 'precursorMz',
                      'sirius_compound_name', 'sirius_cosmic_confidence',
                      'npc_pathway', 'npc_superclass', 'npc_class',
                      'smiles', 'inchikey']
        with open(output_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
        print(f"\nWrote empty sirius_annotations.csv (SIRIUS not available)")
        return str(output_csv)

    print(f"\nRunning SIRIUS on {mgf_path}...")
    success = run_sirius(str(mgf_path), str(output_dir), sirius_cmd)

    sirius_out = output_dir / "sirius_out"
    summaries_dir = sirius_out / "summaries"

    if success and summaries_dir.exists():
        print("\nParsing SIRIUS results...")
        formula_results = parse_formula_identifications(str(summaries_dir))
        canopus_results = parse_canopus_summary(str(summaries_dir))

        output_csv = output_dir / "sirius_annotations.csv"
        merge_sirius_results(formula_results, canopus_results, str(output_csv))
    else:
        print("\nSIRIUS did not produce expected output — writing empty annotations.")
        output_csv = output_dir / "sirius_annotations.csv"
        fieldnames = ['id', 'sirius_formula', 'adduct', 'precursorMz',
                      'sirius_compound_name', 'sirius_cosmic_confidence',
                      'npc_pathway', 'npc_superclass', 'npc_class',
                      'smiles', 'inchikey']
        with open(output_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

    print("\nStep 3 complete.")
    return str(output_csv)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 03_sirius_runner.py <mgf_path> [output_dir]")
        print("  mgf_path:   Path to query MGF file")
        print("  output_dir: Output directory (default: data/output/)")
        sys.exit(1)

    base = Path(__file__).resolve().parent.parent
    mgf = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else str(base / "data" / "output")
    run_sirius_pipeline(mgf, out)
