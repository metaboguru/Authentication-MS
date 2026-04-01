#!/usr/bin/env python3
"""
Step 0: Reference Handler
Checks for authentic reference mzML/MGF in data/reference/.
If found, performs direct spectral comparison against query spectra.
"""

import os
import sys
import json
import glob
import csv
from pathlib import Path

def ppm_to_da(mz, ppm=5.0):
    """Convert ppm tolerance to Da for a given m/z value."""
    return mz * ppm / 1e6

def find_reference_files(reference_dir):
    """Find mzML or MGF files in the reference directory."""
    ref_files = []
    for ext in ['*.mzML', '*.mzml', '*.mgf', '*.MGF']:
        ref_files.extend(glob.glob(os.path.join(reference_dir, ext)))
    return ref_files

def load_spectra_from_file(filepath):
    """Load spectra from mzML or MGF file using matchms."""
    try:
        from matchms.importing import load_from_mzml, load_from_mgf
    except ImportError:
        print("ERROR: matchms is required. Install with: pip install matchms")
        sys.exit(1)

    ext = Path(filepath).suffix.lower()
    if ext == '.mzml':
        spectra = list(load_from_mzml(filepath))
    elif ext == '.mgf':
        spectra = list(load_from_mgf(filepath))
    else:
        print(f"ERROR: Unsupported file format: {ext}")
        return []

    print(f"  Loaded {len(spectra)} spectra from {filepath}")
    return spectra

def apply_filters(spectra):
    """Apply standard matchms filters to spectra."""
    from matchms.filtering import default_filters, normalize_intensities, select_by_intensity, select_by_mz

    filtered = []
    for s in spectra:
        if s is None:
            continue
        s = default_filters(s)
        if s is None:
            continue
        s = normalize_intensities(s)
        if s is None:
            continue
        s = select_by_intensity(s, intensity_from=0.01)
        if s is None:
            continue
        s = select_by_mz(s, mz_from=50, mz_to=2000)
        if s is not None and s.peaks.mz.size > 0:
            filtered.append(s)
    return filtered

def compare_spectra(query_spectra, reference_spectra):
    """Compare query vs reference spectra using CosineGreedy and PrecursorMzMatch."""
    from matchms.similarity import CosineGreedy, PrecursorMzMatch

    results = []

    cosine_sim = CosineGreedy(tolerance=0.005, mz_power=0.5, intensity_power=1.0)
    precursor_sim = PrecursorMzMatch(tolerance=5.0, tolerance_type="ppm")

    for i, query in enumerate(query_spectra):
        best_cosine = 0.0
        best_matched_peaks = 0
        best_ref_idx = -1
        precursor_match = False
        query_mz = query.get("precursor_mz") or 0.0
        query_rt = query.get("retention_time") or 0.0

        for j, ref in enumerate(reference_spectra):
            try:
                cosine_result = cosine_sim.pair(query, ref)
                score = cosine_result.score if hasattr(cosine_result, 'score') else float(cosine_result[0])
                matched = cosine_result.matches if hasattr(cosine_result, 'matches') else int(cosine_result[1])
            except Exception:
                score = 0.0
                matched = 0

            if score > best_cosine:
                best_cosine = score
                best_matched_peaks = matched
                best_ref_idx = j

            try:
                prec_result = precursor_sim.pair(query, ref)
                prec_score = float(prec_result) if not hasattr(prec_result, 'score') else prec_result.score
                if prec_score > 0:
                    precursor_match = True
            except Exception:
                pass

        if best_cosine >= 0.9:
            flag = "MATCH"
        elif best_cosine >= 0.7:
            flag = "PARTIAL_MATCH"
        elif best_cosine >= 0.4:
            flag = "WEAK_MATCH"
        else:
            flag = "NO_MATCH"

        feature_id = query.get("feature_id") or f"F{i+1}"

        results.append({
            'feature_id': feature_id,
            'query_mz': round(query_mz, 4),
            'query_rt': round(query_rt, 2),
            'best_cosine': round(best_cosine, 4),
            'matched_peaks': best_matched_peaks,
            'precursor_match': precursor_match,
            'flag': flag,
            'ppm_tolerance_da': round(ppm_to_da(query_mz, 5.0), 6)
        })

    return results

def run_reference_handler(query_mgf_path=None, reference_dir=None, output_dir=None):
    """Main reference handler logic."""
    base_dir = Path(__file__).resolve().parent.parent
    if reference_dir is None:
        reference_dir = base_dir / "data" / "reference"
    else:
        reference_dir = Path(reference_dir)

    if output_dir is None:
        output_dir = base_dir / "data" / "output"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    config_path = output_dir / "pipeline_config.json"

    ref_files = find_reference_files(str(reference_dir))

    if not ref_files:
        print("=" * 60)
        print("STEP 0: Reference Handler")
        print("=" * 60)
        print(f"No reference files found in {reference_dir}")
        print("Pipeline will use spectral libraries + literature only.")
        print()

        config = {
            'has_reference': False,
            'ppm': 5,
            'mode': 'DDA',
            'instrument': 'Orbitrap Exploris 120',
            'reference_file': None
        }
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"Wrote pipeline_config.json to {config_path}")
        return config

    print("=" * 60)
    print("STEP 0: Reference Handler")
    print("=" * 60)
    print(f"Found reference file(s): {ref_files}")

    ref_file = ref_files[0]
    print(f"\nUsing reference: {ref_file}")
    print("Loading reference spectra...")
    reference_spectra = load_spectra_from_file(ref_file)
    reference_spectra = apply_filters(reference_spectra)
    print(f"  {len(reference_spectra)} reference spectra after filtering")

    if query_mgf_path and os.path.exists(query_mgf_path):
        print(f"\nLoading query spectra from {query_mgf_path}...")
        query_spectra = load_spectra_from_file(query_mgf_path)
        query_spectra = apply_filters(query_spectra)
        print(f"  {len(query_spectra)} query spectra after filtering")

        if query_spectra and reference_spectra:
            print("\nRunning spectral comparison (CosineGreedy + PrecursorMzMatch)...")
            results = compare_spectra(query_spectra, reference_spectra)

            comparison_path = output_dir / "reference_comparison.csv"
            if results:
                fieldnames = results[0].keys()
                with open(comparison_path, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(results)
                print(f"\nWrote reference_comparison.csv ({len(results)} features)")

                match_count = sum(1 for r in results if r['flag'] == 'MATCH')
                partial_count = sum(1 for r in results if r['flag'] == 'PARTIAL_MATCH')
                weak_count = sum(1 for r in results if r['flag'] == 'WEAK_MATCH')
                no_match_count = sum(1 for r in results if r['flag'] == 'NO_MATCH')

                print(f"  MATCH (>=0.9):         {match_count}")
                print(f"  PARTIAL_MATCH (>=0.7): {partial_count}")
                print(f"  WEAK_MATCH (>=0.4):    {weak_count}")
                print(f"  NO_MATCH (<0.4):       {no_match_count}")
        else:
            print("WARNING: No spectra available for comparison.")
    else:
        print("\nNo query MGF provided yet — reference comparison will run after Step 1.")
        print("Reference file is registered for later comparison.")

    config = {
        'has_reference': True,
        'ppm': 5,
        'mode': 'DDA',
        'instrument': 'Orbitrap Exploris 120',
        'reference_file': str(ref_file)
    }
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"\nWrote pipeline_config.json to {config_path}")

    return config


if __name__ == "__main__":
    query_mgf = sys.argv[1] if len(sys.argv) > 1 else None
    ref_dir = sys.argv[2] if len(sys.argv) > 2 else None
    out_dir = sys.argv[3] if len(sys.argv) > 3 else None
    run_reference_handler(query_mgf, ref_dir, out_dir)
