#!/usr/bin/env python3
"""
Step 4: Literature Search & Authentication Verdict
Queries PubMed, LOTUS, PubChem, HMDB for compound verification.
Calculates authentication verdict based on match rates.
"""

import os
import sys
import json
import csv
import time
from pathlib import Path

import requests
import pandas as pd


# Rate limiting
PUBMED_DELAY = 0.35  # seconds between PubMed calls
HMDB_DELAY = 0.4     # seconds between HMDB calls


def query_pubmed(compound_name, plant_genus, max_results=5):
    """Search PubMed via NCBI eutils for compound-plant associations."""
    if not compound_name or not plant_genus:
        return 0, []

    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    search_term = f'"{compound_name}" AND "{plant_genus}"'

    try:
        search_url = f"{base_url}/esearch.fcgi"
        params = {
            'db': 'pubmed',
            'term': search_term,
            'retmax': max_results,
            'retmode': 'json'
        }
        resp = requests.get(search_url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        result = data.get('esearchresult', {})
        count = int(result.get('count', 0))
        pmids = result.get('idlist', [])

        return count, pmids
    except Exception as e:
        print(f"    PubMed query failed for '{compound_name}': {e}")
        return 0, []


def query_lotus(compound_name):
    """Search LOTUS for natural product-organism associations."""
    if not compound_name:
        return [], []

    try:
        url = "https://lotus.naturalproducts.net/api/search/simple"
        params = {'query': compound_name}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        organisms = []
        families = []

        if isinstance(data, list):
            for entry in data[:20]:
                org = entry.get('organismCleaned', {})
                if isinstance(org, dict):
                    org_name = org.get('name', '')
                    org_family = org.get('family', '')
                elif isinstance(org, str):
                    org_name = org
                    org_family = ''
                else:
                    continue

                if org_name and org_name not in organisms:
                    organisms.append(org_name)
                if org_family and org_family not in families:
                    families.append(org_family)
        elif isinstance(data, dict):
            natural_products = data.get('naturalProducts', [])
            for np_entry in natural_products[:20]:
                org_list = np_entry.get('organisms', [])
                for org in org_list:
                    org_name = org.get('name', '') if isinstance(org, dict) else str(org)
                    if org_name and org_name not in organisms:
                        organisms.append(org_name)

        return organisms, families
    except Exception as e:
        print(f"    LOTUS query failed for '{compound_name}': {e}")
        return [], []


def query_lotus_wikidata(compound_name, plant_genus):
    """Fallback: Query Wikidata SPARQL for plant-compound taxonomy."""
    if not compound_name:
        return False

    sparql_query = f"""
    SELECT ?compound ?compoundLabel ?taxon ?taxonLabel WHERE {{
      ?compound wdt:P31 wd:Q11173 .
      ?compound rdfs:label ?compoundLabel .
      FILTER(CONTAINS(LCASE(?compoundLabel), LCASE("{compound_name}")))
      ?compound wdt:P703 ?taxon .
      ?taxon rdfs:label ?taxonLabel .
      FILTER(CONTAINS(LCASE(?taxonLabel), LCASE("{plant_genus}")))
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 5
    """

    try:
        url = "https://query.wikidata.org/sparql"
        params = {'query': sparql_query, 'format': 'json'}
        headers = {'User-Agent': 'KewAuthPipeline/1.0 (authentication research)'}
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        bindings = data.get('results', {}).get('bindings', [])
        return len(bindings) > 0
    except Exception:
        return False


def query_pubchem(compound_name):
    """Query PubChem for structural confirmation."""
    try:
        import pubchempy as pcp
        results = pcp.get_compounds(compound_name, 'name')
        if results:
            c = results[0]
            return {
                'cid': c.cid,
                'formula': c.molecular_formula or '',
                'smiles': c.isomeric_smiles or c.canonical_smiles or '',
                'iupac_name': c.iupac_name or ''
            }
    except ImportError:
        print("    WARNING: pubchempy not installed. Skipping PubChem queries.")
    except Exception as e:
        print(f"    PubChem query failed for '{compound_name}': {e}")

    return {'cid': '', 'formula': '', 'smiles': '', 'iupac_name': ''}


def query_hmdb(compound_name):
    """Query HMDB for metabolite identity confirmation."""
    if not compound_name:
        return ''

    try:
        url = "https://hmdb.ca/unearth/q"
        params = {
            'query': compound_name,
            'searcher': 'metabolites',
            'button': ''
        }
        headers = {
            'User-Agent': 'KewAuthPipeline/1.0',
            'Accept': 'text/html'
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)

        if resp.status_code == 200:
            text = resp.text
            import re
            hmdb_ids = re.findall(r'HMDB\d{7}', text)
            if hmdb_ids:
                return hmdb_ids[0]
    except Exception as e:
        print(f"    HMDB query failed for '{compound_name}': {e}")

    return ''


def calculate_verdict(verified_df, has_reference, ref_match_rate=0.0):
    """Calculate authentication verdict."""
    total_l1_l2 = len(verified_df[verified_df['annotation_level'].isin([1, 2])])
    confirmed = len(verified_df[verified_df['literature_confirmed'] == 'YES'])

    if total_l1_l2 > 0:
        confirmation_rate = confirmed / total_l1_l2
    else:
        confirmation_rate = 0.0

    if has_reference and ref_match_rate >= 0.70:
        verdict = "AUTHENTIC (Reference-Confirmed)"
        confidence = f"Reference match rate: {ref_match_rate:.1%}"
    elif confirmation_rate >= 0.70:
        verdict = "AUTHENTIC (Literature-Confirmed)"
        confidence = f"Literature confirmation rate: {confirmation_rate:.1%} ({confirmed}/{total_l1_l2})"
    elif confirmation_rate >= 0.40:
        verdict = "PROBABLE"
        confidence = f"Literature confirmation rate: {confirmation_rate:.1%} ({confirmed}/{total_l1_l2})"
    else:
        verdict = "INCONCLUSIVE/SUSPECT"
        confidence = f"Literature confirmation rate: {confirmation_rate:.1%} ({confirmed}/{total_l1_l2})"

    return verdict, confidence, confirmation_rate


def run_literature_search(output_dir, plant_genus=None, claimed_species=None):
    """Main literature search function."""
    print("=" * 60)
    print("STEP 4: Literature Search & Verification")
    print("=" * 60)

    output_dir = Path(output_dir)

    # Load pipeline config
    config_path = output_dir / "pipeline_config.json"
    has_reference = False
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
        has_reference = config.get('has_reference', False)

    # Load merged annotations
    annotations_path = output_dir / "merged_annotations.csv"
    if not annotations_path.exists():
        print(f"ERROR: merged_annotations.csv not found in {output_dir}")
        sys.exit(1)

    ann_df = pd.read_csv(annotations_path)
    print(f"  Loaded {len(ann_df)} annotations")

    # Load SIRIUS annotations if available
    sirius_path = output_dir / "sirius_annotations.csv"
    sirius_df = None
    if sirius_path.exists():
        sirius_df = pd.read_csv(sirius_path)
        if len(sirius_df) > 0:
            print(f"  Loaded {len(sirius_df)} SIRIUS annotations")

            # Upgrade confidence for SIRIUS COSMIC matches
            for idx, row in sirius_df.iterrows():
                try:
                    cosmic = float(row.get('sirius_cosmic_confidence', 0))
                    if cosmic >= 0.5:
                        # Find matching feature in annotations and upgrade to Level 2
                        sirius_id = str(row.get('id', ''))
                        mask = ann_df['feature_id'].astype(str) == sirius_id
                        if mask.any():
                            current_level = ann_df.loc[mask, 'annotation_confidence_level'].values[0]
                            if current_level > 2:
                                ann_df.loc[mask, 'annotation_confidence_level'] = 2
                except (ValueError, TypeError):
                    pass

    # Filter to Level 1 and Level 2 for literature search
    l1_l2 = ann_df[ann_df['annotation_confidence_level'].isin([1, 2])].copy()
    print(f"  {len(l1_l2)} Level 1/2 compounds to verify")

    if plant_genus is None:
        plant_genus = ""
    if claimed_species is None:
        claimed_species = ""

    # Literature verification
    verified_rows = []
    for idx, row in l1_l2.iterrows():
        compound = row.get('best_match_name', '')
        if not compound:
            continue

        print(f"\n  Verifying: {compound} (m/z {row['mz']}, RT {row['rt']} min)")

        # PubMed
        pubmed_hits, pmids = query_pubmed(compound, plant_genus)
        time.sleep(PUBMED_DELAY)
        print(f"    PubMed: {pubmed_hits} hits")

        # LOTUS
        lotus_organisms, lotus_families = query_lotus(compound)
        time.sleep(0.3)

        # LOTUS Wikidata fallback
        wikidata_found = False
        if not lotus_organisms and plant_genus:
            wikidata_found = query_lotus_wikidata(compound, plant_genus)
            time.sleep(0.3)

        # PubChem
        pubchem = query_pubchem(compound)
        time.sleep(0.3)

        # HMDB
        hmdb_id = query_hmdb(compound)
        time.sleep(HMDB_DELAY)

        # Determine if literature-confirmed
        genus_lower = plant_genus.lower() if plant_genus else ""
        species_lower = claimed_species.lower() if claimed_species else ""

        confirmed = False
        if pubmed_hits > 0:
            confirmed = True
        elif any(genus_lower in org.lower() for org in lotus_organisms if genus_lower):
            confirmed = True
        elif any(species_lower in org.lower() for org in lotus_organisms if species_lower):
            confirmed = True
        elif wikidata_found:
            confirmed = True

        verified_rows.append({
            'compound': compound,
            'feature_id': row['feature_id'],
            'mz': row['mz'],
            'rt': row['rt'],
            'claimed_species': claimed_species,
            'literature_confirmed': 'YES' if confirmed else 'NO',
            'pubmed_hits': pubmed_hits,
            'pubmed_ids': ';'.join(pmids[:5]),
            'lotus_organisms': ';'.join(lotus_organisms[:10]),
            'lotus_families': ';'.join(lotus_families[:5]),
            'pubchem_cid': pubchem['cid'],
            'hmdb_id': hmdb_id,
            'annotation_level': row['annotation_confidence_level'],
        })

    # Write literature verification CSV
    lit_csv = output_dir / "literature_verification.csv"
    if verified_rows:
        fieldnames = verified_rows[0].keys()
        with open(lit_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(verified_rows)
        print(f"\n\nWrote literature_verification.csv ({len(verified_rows)} compounds)")
    else:
        print("\nNo Level 1/2 compounds to verify.")
        with open(lit_csv, 'w') as f:
            f.write("compound,feature_id,mz,rt,claimed_species,literature_confirmed,"
                    "pubmed_hits,pubmed_ids,lotus_organisms,lotus_families,"
                    "pubchem_cid,hmdb_id,annotation_level\n")

    # Calculate reference match rate
    ref_match_rate = 0.0
    if has_reference:
        ref_csv = output_dir / "reference_comparison.csv"
        if ref_csv.exists():
            ref_df = pd.read_csv(ref_csv)
            total = len(ref_df)
            matches = len(ref_df[ref_df['flag'] == 'MATCH'])
            ref_match_rate = matches / total if total > 0 else 0.0
            print(f"\n  Reference match rate: {ref_match_rate:.1%} ({matches}/{total})")

    # Calculate verdict
    verified_df = pd.DataFrame(verified_rows) if verified_rows else pd.DataFrame(
        columns=['compound', 'literature_confirmed', 'annotation_level'])
    verdict, confidence, _ = calculate_verdict(verified_df, has_reference, ref_match_rate)

    # Write verdict
    verdict_path = output_dir / "verdict.txt"
    with open(verdict_path, 'w') as f:
        f.write(f"Authentication Verdict: {verdict}\n")
        f.write(f"Confidence: {confidence}\n")
        f.write(f"Reference Available: {has_reference}\n")
        if has_reference:
            f.write(f"Reference Match Rate: {ref_match_rate:.1%}\n")
        f.write(f"Claimed Species: {claimed_species}\n")
        f.write(f"Plant Genus: {plant_genus}\n")
        f.write(f"Total Level 1/2 Compounds: {len(l1_l2)}\n")
        confirmed_count = len(verified_df[verified_df['literature_confirmed'] == 'YES']) if len(verified_df) > 0 else 0
        f.write(f"Literature Confirmed: {confirmed_count}\n")

    print("\n" + "=" * 60)
    print(f"AUTHENTICATION VERDICT: {verdict}")
    print(f"  {confidence}")
    print("=" * 60)
    print(f"\nVerdict saved to {verdict_path}")

    print("\nStep 4 complete.")
    return str(lit_csv), verdict


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 04_literature_search.py <output_dir> [plant_genus] [claimed_species]")
        print("  output_dir:     Directory with merged_annotations.csv")
        print("  plant_genus:    Genus name (e.g., 'Curcuma')")
        print("  claimed_species: Full species (e.g., 'Curcuma longa')")
        sys.exit(1)

    base = Path(__file__).resolve().parent.parent
    out = sys.argv[1] if len(sys.argv) > 1 else str(base / "data" / "output")
    genus = sys.argv[2] if len(sys.argv) > 2 else ""
    species = sys.argv[3] if len(sys.argv) > 3 else ""
    run_literature_search(out, genus, species)
