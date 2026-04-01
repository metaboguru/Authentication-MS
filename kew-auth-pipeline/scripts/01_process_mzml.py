#!/usr/bin/env python3
"""
Step 1: mzML Processing
Validates mzML file and runs MZmine 3 headless batch processing for Orbitrap DDA data.
Outputs GNPS/FBMN MGF and quantification CSV.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from lxml import etree


def validate_mzml(mzml_path):
    """Validate mzML file using pyopenms: count MS1/MS2 scans, detect polarity, check RT range."""
    try:
        import pyopenms
    except ImportError:
        print("ERROR: pyopenms is required. Install with: pip install pyopenms")
        sys.exit(1)

    print(f"Validating mzML file: {mzml_path}")

    exp = pyopenms.MSExperiment()
    pyopenms.MzMLFile().load(str(mzml_path), exp)

    ms1_count = 0
    ms2_count = 0
    polarities = set()
    rt_values = []

    for spec in exp:
        ms_level = spec.getMSLevel()
        if ms_level == 1:
            ms1_count += 1
        elif ms_level == 2:
            ms2_count += 1

        ip = spec.getInstrumentSettings().getPolarity()
        if ip == pyopenms.IonSource.Polarity.POSITIVE:
            polarities.add("positive")
        elif ip == pyopenms.IonSource.Polarity.NEGATIVE:
            polarities.add("negative")

        rt_values.append(spec.getRT())

    rt_min = min(rt_values) / 60.0 if rt_values else 0.0
    rt_max = max(rt_values) / 60.0 if rt_values else 0.0
    polarity_str = "+".join(sorted(polarities)) if polarities else "unknown"

    print(f"  MS1 scans: {ms1_count}")
    print(f"  MS2 scans: {ms2_count}")
    print(f"  Polarity:  {polarity_str}")
    print(f"  RT range:  {rt_min:.2f} - {rt_max:.2f} min")

    if ms2_count == 0:
        print("WARNING: No MS2 scans found — DDA data expected. Check your mzML conversion.")

    return {
        'ms1_count': ms1_count,
        'ms2_count': ms2_count,
        'polarity': polarity_str,
        'rt_min': rt_min,
        'rt_max': rt_max
    }


def generate_mzmine_batch_xml(mzml_path, output_dir):
    """Generate MZmine 3 batch XML for Orbitrap DDA data."""
    mzml_abs = str(Path(mzml_path).resolve())
    output_abs = str(Path(output_dir).resolve())

    batch_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<batch mzmine_version="4">

  <!-- Import raw data -->
  <batchstep method="io.github.mzmine.modules.io.import_rawdata_all.AllSpectralDataImportModule">
    <parameter name="File names">
      <file>{mzml_abs}</file>
    </parameter>
    <parameter name="Advanced import" selected="false"/>
  </batchstep>

  <!-- Mass detection MS1 -->
  <batchstep method="io.github.mzmine.modules.dataprocessing.featdet_massdetection.MassDetectionModule">
    <parameter name="Raw data files" type="BATCH_LAST_FILES"/>
    <parameter name="Scan filters">
      <parameter name="Scan number"/>
      <parameter name="Base Filtering Integer"/>
      <parameter name="Retention time"/>
      <parameter name="Mobility"/>
      <parameter name="MS level filter" selected="1"/>
      <parameter name="Scan definition"/>
      <parameter name="Polarity" value="ANY"/>
      <parameter name="Spectrum type" selected="ANY"/>
    </parameter>
    <parameter name="Scan types (IMS)">NORMAL</parameter>
    <parameter name="Mass detector" selected="Factor of lowest signal">
      <module name="Factor of lowest signal">
        <parameter name="Noise factor">1.5</parameter>
      </module>
      <module name="Centroid">
        <parameter name="Noise level">1.0E5</parameter>
      </module>
      <module name="Exact mass">
        <parameter name="Noise level">1.0E5</parameter>
      </module>
    </parameter>
    <parameter name="Denormalize fragment scans (traps)">false</parameter>
  </batchstep>

  <!-- Mass detection MS2 -->
  <batchstep method="io.github.mzmine.modules.dataprocessing.featdet_massdetection.MassDetectionModule">
    <parameter name="Raw data files" type="BATCH_LAST_FILES"/>
    <parameter name="Scan filters">
      <parameter name="Scan number"/>
      <parameter name="Base Filtering Integer"/>
      <parameter name="Retention time"/>
      <parameter name="Mobility"/>
      <parameter name="MS level filter" selected="2"/>
      <parameter name="Scan definition"/>
      <parameter name="Polarity" value="ANY"/>
      <parameter name="Spectrum type" selected="ANY"/>
    </parameter>
    <parameter name="Scan types (IMS)">NORMAL</parameter>
    <parameter name="Mass detector" selected="Factor of lowest signal">
      <module name="Factor of lowest signal">
        <parameter name="Noise factor">1.5</parameter>
      </module>
      <module name="Centroid">
        <parameter name="Noise level">1.0E4</parameter>
      </module>
      <module name="Exact mass">
        <parameter name="Noise level">1.0E4</parameter>
      </module>
    </parameter>
    <parameter name="Denormalize fragment scans (traps)">true</parameter>
  </batchstep>

  <!-- ADAP Chromatogram builder -->
  <batchstep method="io.github.mzmine.modules.dataprocessing.featdet_adapchromatogrambuilder.ModularADAPChromatogramBuilderModule">
    <parameter name="Raw data files" type="BATCH_LAST_FILES"/>
    <parameter name="Scan filters">
      <parameter name="Scan number"/>
      <parameter name="Base Filtering Integer"/>
      <parameter name="Retention time"/>
      <parameter name="Mobility"/>
      <parameter name="MS level filter" selected="1"/>
      <parameter name="Scan definition"/>
      <parameter name="Polarity" value="ANY"/>
      <parameter name="Spectrum type" selected="ANY"/>
    </parameter>
    <parameter name="Minimum consecutive scans">5</parameter>
    <parameter name="Minimum intensity for consecutive scans">1.0E5</parameter>
    <parameter name="m/z tolerance (scan-to-scan)">
      <absolutetolerance>0.0025</absolutetolerance>
      <ppmtolerance>5.0</ppmtolerance>
    </parameter>
    <parameter name="Suffix">chromatograms</parameter>
  </batchstep>

  <!-- Smoothing (optional) -->
  <batchstep method="io.github.mzmine.modules.dataprocessing.featdet_smoothing.SmoothingModule">
    <parameter name="Feature lists" type="BATCH_LAST_FEATURELISTS"/>
    <parameter name="Smoothing algorithm" selected="Savitzky Golay">
      <module name="Savitzky Golay">
        <parameter name="Filter width">5</parameter>
      </module>
      <module name="Loess">
        <parameter name="Bandwidth">0.05</parameter>
      </module>
    </parameter>
    <parameter name="Suffix">smoothed</parameter>
    <parameter name="Remove original feature list">true</parameter>
  </batchstep>

  <!-- Minimum search resolver -->
  <batchstep method="io.github.mzmine.modules.dataprocessing.featdet_chromatogramdeconvolution.minimumsearch.MinimumSearchFeatureResolverModule">
    <parameter name="Feature lists" type="BATCH_LAST_FEATURELISTS"/>
    <parameter name="Suffix">resolved</parameter>
    <parameter name="Original feature list">REMOVE</parameter>
    <parameter name="MS/MS scan pairing">
      <parameter name="MS1 to MS2 precursor tolerance (m/z)">
        <absolutetolerance>0.01</absolutetolerance>
        <ppmtolerance>5.0</ppmtolerance>
      </parameter>
      <parameter name="RT filter" selected="Use feature edge RT range"/>
    </parameter>
    <parameter name="Dimension">Retention time</parameter>
    <parameter name="Chromatographic threshold">0.01</parameter>
    <parameter name="Minimum search range RT/Mobility (absolute)">0.02</parameter>
    <parameter name="Minimum relative height">0.0</parameter>
    <parameter name="Minimum absolute height">1.0E5</parameter>
    <parameter name="Min ratio of peak top/edge">2.0</parameter>
    <parameter name="Peak duration range (min/mobility)">
      <min>0.02</min>
      <max>2.0</max>
    </parameter>
    <parameter name="Minimum scans (data points)">5</parameter>
  </batchstep>

  <!-- Isotope grouper -->
  <batchstep method="io.github.mzmine.modules.dataprocessing.filter_isotopegrouper.IsotopeGrouperModule">
    <parameter name="Feature lists" type="BATCH_LAST_FEATURELISTS"/>
    <parameter name="Name suffix">deisotoped</parameter>
    <parameter name="m/z tolerance">
      <absolutetolerance>0.0025</absolutetolerance>
      <ppmtolerance>5.0</ppmtolerance>
    </parameter>
    <parameter name="Retention time tolerance" type="absolute">0.05</parameter>
    <parameter name="Monotonic shape">true</parameter>
    <parameter name="Maximum charge">2</parameter>
    <parameter name="Representative isotope">Most intense</parameter>
    <parameter name="Never remove feature with MS2">true</parameter>
    <parameter name="Original feature list">REMOVE</parameter>
  </batchstep>

  <!-- Filter rows: only keep features with MS2 -->
  <batchstep method="io.github.mzmine.modules.dataprocessing.filter_rowsfilter.RowsFilterModule">
    <parameter name="Feature lists" type="BATCH_LAST_FEATURELISTS"/>
    <parameter name="Name suffix">filtered</parameter>
    <parameter name="Minimum features in a row">1</parameter>
    <parameter name="Minimum features in an isotope pattern">0</parameter>
    <parameter name="Reset the feature number ID">true</parameter>
    <parameter name="Keep only features with MS2 scan (FBMN)">true</parameter>
    <parameter name="Original feature list">REMOVE</parameter>
  </batchstep>

  <!-- GNPS/FBMN Export -->
  <batchstep method="io.github.mzmine.modules.io.export_features_gnps.fbmn.GnpsFbmnExportAndSubmitModule">
    <parameter name="Feature lists" type="BATCH_LAST_FEATURELISTS"/>
    <parameter name="Filename">
      <current_file>{output_abs}/gnps_export</current_file>
    </parameter>
    <parameter name="Merge MS/MS (experimental)" selected="true">
      <parameter name="Select spectra to merge">across samples</parameter>
      <parameter name="m/z merge mode" selected="weighted average (remove outliers)"/>
      <parameter name="Intensity merge mode" selected="sum all intensities"/>
      <parameter name="Expected mass deviation">
        <absolutetolerance>0.0025</absolutetolerance>
        <ppmtolerance>5.0</ppmtolerance>
      </parameter>
      <parameter name="Cosine threshold (%)">10.0</parameter>
      <parameter name="Signal count threshold (%)">20.0</parameter>
    </parameter>
    <parameter name="Filter rows">MS2 OR ION IDENTITY</parameter>
    <parameter name="Feature intensity">Height</parameter>
    <parameter name="Submit to GNPS">false</parameter>
  </batchstep>

</batch>
"""
    return batch_xml


def check_mzmine_installed():
    """Check if MZmine 3 is available on the system."""
    mzmine_cmd = shutil.which("mzmine")
    if mzmine_cmd:
        return mzmine_cmd

    common_paths = [
        "/opt/mzmine/bin/mzmine",
        "/usr/local/bin/mzmine",
        os.path.expanduser("~/MZmine/mzmine"),
        os.path.expanduser("~/mzmine/bin/mzmine"),
        "C:\\Program Files\\MZmine\\mzmine.exe",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p

    return None


def run_mzmine_batch(batch_xml_path, mzmine_cmd):
    """Run MZmine 3 in headless batch mode."""
    cmd = [mzmine_cmd, "--batch", str(batch_xml_path), "--headless"]
    print(f"  Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600
        )
        if result.returncode != 0:
            print(f"  MZmine STDERR:\n{result.stderr[:2000]}")
            print(f"  MZmine STDOUT:\n{result.stdout[:2000]}")
            return False
        print("  MZmine batch completed successfully.")
        return True
    except subprocess.TimeoutExpired:
        print("ERROR: MZmine batch timed out after 60 minutes.")
        return False
    except Exception as e:
        print(f"ERROR running MZmine: {e}")
        return False


def process_mzml(mzml_path, output_dir):
    """Main processing function."""
    mzml_path = Path(mzml_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("STEP 1: mzML Processing")
    print("=" * 60)

    if not mzml_path.exists():
        print(f"ERROR: mzML file not found: {mzml_path}")
        sys.exit(1)

    info = validate_mzml(str(mzml_path))

    mzmine_cmd = check_mzmine_installed()
    if not mzmine_cmd:
        print("\n" + "=" * 60)
        print("ERROR: MZmine 3 is not installed or not in PATH.")
        print("")
        print("Install MZmine 3:")
        print("  1. Download from https://mzmine.github.io/mzmine_documentation/getting_started.html")
        print("  2. Linux: Extract and add to PATH:")
        print("     export PATH=$PATH:/path/to/MZmine/bin")
        print("  3. macOS: Install .dmg and link:")
        print("     ln -s /Applications/MZmine.app/Contents/MacOS/mzmine /usr/local/bin/mzmine")
        print("  4. Windows: Add MZmine install dir to PATH")
        print("=" * 60)
        sys.exit(1)

    print(f"\nMZmine found at: {mzmine_cmd}")

    print("\nGenerating MZmine batch XML...")
    batch_xml = generate_mzmine_batch_xml(str(mzml_path), str(output_dir))

    batch_path = output_dir / "mzmine_batch.xml"
    with open(batch_path, 'w') as f:
        f.write(batch_xml)
    print(f"  Batch XML saved to: {batch_path}")

    print("\nRunning MZmine 3 headless batch processing...")
    success = run_mzmine_batch(batch_path, mzmine_cmd)

    if not success:
        print("ERROR: MZmine batch processing failed.")
        sys.exit(1)

    mgf_path = output_dir / "gnps_export.mgf"
    quant_path = output_dir / "gnps_export_quant.csv"

    if mgf_path.exists():
        print(f"\n  MGF output: {mgf_path} ({mgf_path.stat().st_size} bytes)")
    else:
        print(f"WARNING: Expected MGF not found at {mgf_path}")

    if quant_path.exists():
        print(f"  Quant CSV:  {quant_path} ({quant_path.stat().st_size} bytes)")
    else:
        print(f"WARNING: Expected quant CSV not found at {quant_path}")

    print("\nStep 1 complete.")
    return {
        'mgf_path': str(mgf_path),
        'quant_path': str(quant_path),
        'validation': info
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 01_process_mzml.py <mzml_path> [output_dir]")
        print("  mzml_path:  Path to input .mzML file")
        print("  output_dir: Output directory (default: data/output/)")
        sys.exit(1)

    mzml_file = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parent.parent / "data" / "output")
    process_mzml(mzml_file, out_dir)
