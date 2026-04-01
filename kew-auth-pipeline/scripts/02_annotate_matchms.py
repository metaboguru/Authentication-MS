#!/usr/bin/env python3
"""
Step 2: Spectral Annotation with matchms
Loads query MGF and spectral libraries, runs CosineGreedy, ModifiedCosine,
PrecursorMzMatch, MS2DeepScore, and MS2Query. Merges all scores.
"""

import os
import sys
import json
import glob
import csv
from pathlib import Path

import numpy as np


def ppm_to_da(mz, ppm=5.0):
    """Convert ppm tolerance to Da, capped at 0.005 Da for Orbitrap."""
    da = mz * ppm / 1e6
    return min(da, 0.005)


def load_spectra(filepath):
    """Load spectra from MGF file."""
    from matchms.importing import load_from_mgf
    spectra = list(load_from_mgf(filepath))
    print(f"  Loaded {len(spectra)} spectra from {Path(filepath).name}")
    return spectra


def apply_filters(spectra):
    """Apply standard matchms filtering pipeline."""
    from matchms.filtering import (
        default_filters, add_parent_mass, normalize_intensities,
        select_by_intensity, select_by_mz, reduce_to_number_of_peaks
    )

    filtered = []
    for s in spectra:
        if s is None:
            continue
        s = default_filters(s)
        if s is None:
            continue
        s = add_parent_mass(s)
        if s is None:
            continue
        s = normalize_intensities(s)
        if s is None:
            continue
        s = select_by_intensity(s, intensity_from=0.01)
        if s is None:
            continue
        s = select_by_mz(s, mz_from=50, mz_to=2000)
        if s is None:
            continue
        s = reduce_to_number_of_peaks(s, n_max=500)
        if s is not None and s.peaks.mz.size > 0:
            filtered.append(s)
    return filtered


def find_library_files(libraries_dir):
    """Find all MGF spectral library files in the libraries directory."""
    lib_files = []
    for ext in ['*.mgf', '*.MGF']:
        lib_files.extend(glob.glob(os.path.join(libraries_dir, ext)))

    # Exclude ms2deepscore model files
    lib_files = [f for f in lib_files if 'ms2deepscore' not in Path(f).name.lower()]
    return lib_files


def run_cosine_greedy(queries, references, tolerance=0.005):
    """Run CosineGreedy matching."""
    from matchms.similarity import CosineGreedy

    cosine = CosineGreedy(tolerance=tolerance, mz_power=0.5, intensity_power=1.0)
    results = {}

    for i, query in enumerate(queries):
        best_score = 0.0
        best_matches = 0
        best_ref = None
        best_lib = ""

        for j, ref in enumerate(references):
            try:
                result = cosine.pair(query, ref)
                score = float(result.score) if hasattr(result, 'score') else float(result[0])
                matched = int(result.matches) if hasattr(result, 'matches') else int(result[1])
            except Exception:
                score = 0.0
                matched = 0

            if score > best_score:
                best_score = score
                best_matches = matched
                best_ref = ref
                best_lib = ref.get("library") or ref.get("source") or "unknown"

        feature_id = query.get("feature_id") or f"F{i+1}"
        results[feature_id] = {
            'cosine_score': round(best_score, 4),
            'cosine_matched_peaks': best_matches,
            'best_ref': best_ref,
            'library_source': best_lib
        }

    return results


def run_modified_cosine(queries, references, tolerance=0.005):
    """Run ModifiedCosine matching."""
    from matchms.similarity import ModifiedCosine

    mod_cosine = ModifiedCosine(tolerance=tolerance, mz_power=0.5, intensity_power=1.0)
    results = {}

    for i, query in enumerate(queries):
        best_score = 0.0

        for ref in references:
            try:
                result = mod_cosine.pair(query, ref)
                score = float(result.score) if hasattr(result, 'score') else float(result[0])
            except Exception:
                score = 0.0

            if score > best_score:
                best_score = score

        feature_id = query.get("feature_id") or f"F{i+1}"
        results[feature_id] = {'modified_cosine_score': round(best_score, 4)}

    return results


def run_precursor_match(queries, references):
    """Run PrecursorMzMatch."""
    from matchms.similarity import PrecursorMzMatch

    prec_match = PrecursorMzMatch(tolerance=5.0, tolerance_type="ppm")
    results = {}

    for i, query in enumerate(queries):
        matched = False
        for ref in references:
            try:
                result = prec_match.pair(query, ref)
                score = float(result) if not hasattr(result, 'score') else float(result.score)
                if score > 0:
                    matched = True
                    break
            except Exception:
                pass

        feature_id = query.get("feature_id") or f"F{i+1}"
        results[feature_id] = {'precursor_match': matched}

    return results


def run_ms2deepscore(queries, references, model_path):
    """Run MS2DeepScore if model file exists."""
    try:
        from ms2deepscore import MS2DeepScore
        from ms2deepscore.models import load_model
    except ImportError:
        print("  WARNING: ms2deepscore not installed. Skipping MS2DeepScore.")
        return {}

    if not os.path.exists(model_path):
        print(f"  WARNING: MS2DeepScore model not found at {model_path}. Skipping.")
        return {}

    print("  Loading MS2DeepScore model...")
    try:
        model = load_model(model_path)
        scorer = MS2DeepScore(model)
    except Exception as e:
        print(f"  WARNING: Failed to load MS2DeepScore model: {e}. Skipping.")
        return {}

    results = {}
    for i, query in enumerate(queries):
        best_score = 0.0
        for ref in references:
            try:
                score = float(scorer.pair(query, ref))
                if score > best_score:
                    best_score = score
            except Exception:
                pass

        feature_id = query.get("feature_id") or f"F{i+1}"
        results[feature_id] = {'ms2deepscore_score': round(best_score, 4)}

    return results


def run_ms2query(queries, ms2query_dir):
    """Run MS2Query if library exists."""
    try:
        from ms2query.ms2library import MS2Library
        from ms2query.run_ms2query import run_ms2query_on_spectra
    except ImportError:
        print("  WARNING: ms2query not installed. Skipping MS2Query.")
        return {}

    if not os.path.isdir(ms2query_dir):
        print(f"  WARNING: MS2Query library not found at {ms2query_dir}. Skipping.")
        return {}

    try:
        ms2library = MS2Library(ms2query_dir)
        results_list = run_ms2query_on_spectra(ms2library, queries)
    except Exception as e:
        print(f"  WARNING: MS2Query failed: {e}. Skipping.")
        return {}

    results = {}
    for i, query in enumerate(queries):
        feature_id = query.get("feature_id") or f"F{i+1}"
        score = 0.0
        if i < len(results_list) and results_list[i] is not None:
            score = float(results_list[i].get("ms2query_model_prediction", 0.0))
        results[feature_id] = {'ms2query_score': round(score, 4)}

    return results


def determine_confidence(row, has_reference=False):
    """Determine MSI confidence level."""
    cosine = row.get('cosine_score', 0.0)
    precursor = row.get('precursor_match', False)
    ms2deep = row.get('ms2deepscore_score', 0.0)
    ref_flag = row.get('flag', 'NO_MATCH')

    # Level 1: cosine >= 0.9 AND precursor match, or reference MATCH
    if has_reference and ref_flag == 'MATCH':
        return 1
    if cosine >= 0.9 and precursor:
        return 1

    # Level 2: cosine 0.7-0.9, or SIRIUS COSMIC (handled later)
    if cosine >= 0.7:
        return 2
    if has_reference and ref_flag == 'PARTIAL_MATCH':
        return 2

    # Level 3: MS2DeepScore >= 0.5 only
    if ms2deep >= 0.5:
        return 3

    return 0  # No confident annotation


def annotate(query_mgf_path, libraries_dir, output_dir):
    """Main annotation function."""
    print("=" * 60)
    print("STEP 2: Spectral Annotation (matchms)")
    print("=" * 60)

    query_mgf_path = Path(query_mgf_path)
    libraries_dir = Path(libraries_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load pipeline config
    config_path = output_dir / "pipeline_config.json"
    has_reference = False
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
        has_reference = config.get('has_reference', False)
        print(f"  Reference available: {has_reference}")

    # Load query spectra
    if not query_mgf_path.exists():
        print(f"ERROR: Query MGF not found: {query_mgf_path}")
        sys.exit(1)

    print("\nLoading query spectra...")
    queries = load_spectra(str(query_mgf_path))
    queries = apply_filters(queries)
    print(f"  {len(queries)} query spectra after filtering")

    if not queries:
        print("ERROR: No valid query spectra after filtering.")
        sys.exit(1)

    # Load spectral libraries
    print("\nLoading spectral libraries...")
    lib_files = find_library_files(str(libraries_dir))
    if not lib_files:
        print(f"  WARNING: No spectral library files found in {libraries_dir}")
        print("  Place .mgf library files (GNPS, MassBank, NIST, Fiehn) in libraries/")

    all_references = []
    for lib_file in lib_files:
        lib_name = Path(lib_file).stem
        specs = load_spectra(lib_file)
        for s in specs:
            if s is not None:
                s.set("library", lib_name)
        specs = apply_filters(specs)
        all_references.extend(specs)

    print(f"  Total library spectra: {len(all_references)}")

    # Run matching algorithms
    cosine_results = {}
    modcos_results = {}
    prec_results = {}
    ms2deep_results = {}
    ms2q_results = {}

    if all_references:
        print("\nRunning CosineGreedy (tolerance=0.005 Da, Orbitrap upper bound)...")
        cosine_results = run_cosine_greedy(queries, all_references, tolerance=0.005)

        print("Running ModifiedCosine...")
        modcos_results = run_modified_cosine(queries, all_references, tolerance=0.005)

        print("Running PrecursorMzMatch (5 ppm)...")
        prec_results = run_precursor_match(queries, all_references)
    else:
        print("\nNo library spectra available — skipping spectral matching.")

    # MS2DeepScore
    model_path = libraries_dir / "ms2deepscore_model.pt"
    if all_references:
        print("\nRunning MS2DeepScore...")
        ms2deep_results = run_ms2deepscore(queries, all_references, str(model_path))

    # MS2Query
    ms2query_dir = libraries_dir / "ms2query"
    print("\nRunning MS2Query...")
    ms2q_results = run_ms2query(queries, str(ms2query_dir))

    # Load reference comparison if available
    ref_data = {}
    if has_reference:
        ref_csv = output_dir / "reference_comparison.csv"
        if ref_csv.exists():
            import pandas as pd
            ref_df = pd.read_csv(ref_csv)
            for _, row in ref_df.iterrows():
                ref_data[str(row['feature_id'])] = {
                    'ref_cosine': row.get('best_cosine', 0.0),
                    'flag': row.get('flag', 'NO_MATCH')
                }

    # Merge all results
    print("\nMerging annotations...")
    merged = []
    for i, query in enumerate(queries):
        feature_id = query.get("feature_id") or f"F{i+1}"
        mz = query.get("precursor_mz") or 0.0
        rt = query.get("retention_time") or 0.0

        # Detect ionisation mode
        adduct = query.get("adduct") or ""
        if "+" in adduct or query.get("charge", 0) > 0:
            ion_mode = "positive"
        elif "-" in adduct or query.get("charge", 0) < 0:
            ion_mode = "negative"
        else:
            ion_mode = "unknown"

        cos = cosine_results.get(feature_id, {})
        mcos = modcos_results.get(feature_id, {})
        prec = prec_results.get(feature_id, {})
        deep = ms2deep_results.get(feature_id, {})
        ms2q = ms2q_results.get(feature_id, {})
        ref = ref_data.get(feature_id, {})

        # Get best match name from reference spectrum
        best_name = ""
        smiles = ""
        inchikey = ""
        if cos.get('best_ref') is not None:
            best_ref = cos['best_ref']
            best_name = best_ref.get("compound_name") or best_ref.get("name") or ""
            smiles = best_ref.get("smiles") or ""
            inchikey = best_ref.get("inchikey") or ""

        row = {
            'feature_id': feature_id,
            'mz': round(float(mz), 4),
            'rt': round(float(rt), 2),
            'ionisation_mode': ion_mode,
            'best_match_name': best_name,
            'cosine_score': cos.get('cosine_score', 0.0),
            'cosine_matched_peaks': cos.get('cosine_matched_peaks', 0),
            'modified_cosine_score': mcos.get('modified_cosine_score', 0.0),
            'ms2deepscore_score': deep.get('ms2deepscore_score', 0.0),
            'ms2query_score': ms2q.get('ms2query_score', 0.0),
            'library_source': cos.get('library_source', ''),
            'smiles': smiles,
            'inchikey': inchikey,
            'precursor_match': prec.get('precursor_match', False),
            'ref_cosine': ref.get('ref_cosine', 0.0),
            'flag': ref.get('flag', ''),
        }

        row['annotation_confidence_level'] = determine_confidence(row, has_reference)

        # Only include rows with some annotation
        if (row['cosine_score'] > 0 or row['ms2deepscore_score'] > 0
                or row['ms2query_score'] > 0 or row['ref_cosine'] > 0):
            merged.append(row)

    # Sort by cosine score descending
    merged.sort(key=lambda x: x['cosine_score'], reverse=True)

    # Write output
    output_csv = output_dir / "merged_annotations.csv"
    if merged:
        fieldnames = merged[0].keys()
        with open(output_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(merged)
        print(f"\nWrote merged_annotations.csv ({len(merged)} annotated features)")

        level_counts = {}
        for row in merged:
            lvl = row['annotation_confidence_level']
            level_counts[lvl] = level_counts.get(lvl, 0) + 1

        print(f"  Level 1 (Confirmed): {level_counts.get(1, 0)}")
        print(f"  Level 2 (Probable):  {level_counts.get(2, 0)}")
        print(f"  Level 3 (Putative):  {level_counts.get(3, 0)}")
        print(f"  Unconfident:         {level_counts.get(0, 0)}")
    else:
        print("\nNo annotations above threshold found.")
        with open(output_csv, 'w') as f:
            f.write("feature_id,mz,rt,ionisation_mode,best_match_name,cosine_score,"
                    "cosine_matched_peaks,modified_cosine_score,ms2deepscore_score,"
                    "ms2query_score,library_source,smiles,inchikey,precursor_match,"
                    "ref_cosine,flag,annotation_confidence_level\n")

    print("\nStep 2 complete.")
    return str(output_csv)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 02_annotate_matchms.py <query_mgf> [libraries_dir] [output_dir]")
        print("  query_mgf:     Path to query MGF (from MZmine GNPS export)")
        print("  libraries_dir: Directory with spectral library MGFs (default: libraries/)")
        print("  output_dir:    Output directory (default: data/output/)")
        sys.exit(1)

    base = Path(__file__).resolve().parent.parent
    query = sys.argv[1]
    libs = sys.argv[2] if len(sys.argv) > 2 else str(base / "libraries")
    out = sys.argv[3] if len(sys.argv) > 3 else str(base / "data" / "output")
    annotate(query, libs, out)
