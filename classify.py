"""
Clasifica los materiales del SAP en familias usando family_rules.yaml
y sube el resultado a S3.

Uso:
    python classify.py                    # clasifica y muestra resumen (no sube)
    python classify.py --upload           # clasifica y sube a S3 con fecha
    python classify.py --familia OTROS    # muestra solo una familia
    python classify.py --sample 30        # muestra 30 ejemplos clasificados
"""
import io
import os
import sys
from pathlib import Path

import pandas as pd
import yaml

from s3_utils import build_dated_key, download_bytes, get_bucket, upload_dataframe_as_excel

SAP_FILE_KEY = os.getenv(
    'SAP_FILE_KEY',
    "bedrock/Cajas Especiales Drive/Archivos Excel-CSV/Materiales/Price List MP SAP Ago-2025.xlsx"
)
RULES_PATH = Path(__file__).parent / "family_rules.yaml"
S3_OUTPUT_PREFIX = os.getenv('S3_OUTPUT_PREFIX', 'clasificados/')

# Columnas numéricas que se redondean antes de subir.
# Esto evita que aparezcan valores como 0.00292397660818707 en Excel
# cuando el SAP solo muestra 4 decimales.
NUMERIC_COLUMNS_ROUNDING = {
    'Precio Unit.': 4,
    'Total Value': 2,
    'Total Value $$': 2,
    'Total Stock': 2,
}


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

def load_sap() -> pd.DataFrame:
    print(f"Descargando SAP...")
    data = download_bytes(SAP_FILE_KEY)
    df = pd.read_excel(io.BytesIO(data), dtype=str)
    df = df.dropna(how='all').dropna(axis=1, how='all').reset_index(drop=True)

    # Descartar filas sin Material Description (basura del export)
    before = len(df)
    df = df[df['Material Description'].notna() & (df['Material Description'].str.strip() != '')]
    df = df.reset_index(drop=True)
    after = len(df)
    if before != after:
        print(f"⚠️  Descartadas {before - after} filas sin Material Description")

    print(f"Cargados {after} materiales\n")
    return df


def load_rules() -> dict:
    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Motor de reglas
# ---------------------------------------------------------------------------

def _str_lower(value) -> str:
    if value is None:
        return ''
    if pd.isna(value):
        return ''
    return str(value).lower().strip()


def evaluate_rule(rule: dict, name: str, unit: str) -> bool:
    name_l = name.lower()
    unit_u = unit.upper()

    name_match = rule.get('match_name')
    if name_match:
        starts_with = [s.lower() for s in name_match.get('starts_with', []) or []]
        if starts_with and not any(name_l.startswith(s) for s in starts_with):
            return False
        contains_any = [s.lower() for s in name_match.get('contains_any', []) or []]
        if contains_any and not any(s in name_l for s in contains_any):
            return False
        contains_all = [s.lower() for s in name_match.get('contains_all', []) or []]
        if contains_all and not all(s in name_l for s in contains_all):
            return False
        not_contains = [s.lower() for s in name_match.get('not_contains', []) or []]
        if not_contains and any(s in name_l for s in not_contains):
            return False

    match_unit = rule.get('match_unit')
    if match_unit:
        units = [u.upper() for u in match_unit]
        if unit_u not in units:
            return False

    if not name_match and not match_unit:
        return False
    return True


def classify_row(row: pd.Series, rules: list, default: str) -> tuple[str, int]:
    name = _str_lower(row.get('Material Description'))
    unit = _str_lower(row.get('BUn'))
    for i, rule in enumerate(rules):
        if evaluate_rule(rule, name, unit):
            return rule['familia'], i
    return default, -1


def classify_dataframe(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    rules = config.get('rules', [])
    default = config.get('default_familia', 'OTROS')

    familias = []
    rule_indices = []
    for _, row in df.iterrows():
        fam, idx = classify_row(row, rules, default)
        familias.append(fam)
        rule_indices.append(idx)

    out = df.copy()
    out['familia'] = familias
    out['_rule_index'] = rule_indices
    return out


# ---------------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------------

def print_distribution(df: pd.DataFrame):
    print("=" * 70)
    print("DISTRIBUCIÓN POR FAMILIA")
    print("=" * 70)
    counts = df['familia'].value_counts()
    total = len(df)
    for fam, count in counts.items():
        pct = (count / total) * 100
        bar = '█' * int(pct / 2)
        print(f"  {fam:12} {count:>5,} ({pct:5.1f}%) {bar}")
    print()


def print_rule_usage(df: pd.DataFrame, rules: list):
    print("=" * 70)
    print("USO DE CADA REGLA")
    print("=" * 70)
    counts = df['_rule_index'].value_counts().sort_index()
    for idx, count in counts.items():
        if idx == -1:
            label = "(default → OTROS)"
        else:
            rule = rules[idx]
            label = f"#{idx}: {rule['familia']}"
            mn = rule.get('match_name', {}) or {}
            if mn.get('starts_with'):
                label += f" starts={mn['starts_with']}"
            elif mn.get('contains_any'):
                preview = mn['contains_any'][:3]
                label += f" any={preview}"
            elif rule.get('match_unit'):
                label += f" unit={rule['match_unit']}"
        print(f"  {count:>5,} | {label}")
    print()


def show_samples_per_familia(df: pd.DataFrame, n: int = 5):
    print("=" * 70)
    print(f"MUESTRAS POR FAMILIA (hasta {n} por familia)")
    print("=" * 70)
    for fam in sorted(df['familia'].unique()):
        subset = df[df['familia'] == fam]
        print(f"\n📦 {fam}  ({len(subset)} materiales)")
        for _, row in subset.head(n).iterrows():
            code = str(row.get('Material', ''))[:12]
            desc = str(row.get('Material Description', ''))[:65]
            unit = str(row.get('BUn', ''))[:5]
            print(f"   {code:12} | {unit:4} | {desc}")
    print()


def show_only_familia(df: pd.DataFrame, familia: str, limit: int = 100):
    print("=" * 70)
    print(f"MATERIALES EN FAMILIA: {familia}")
    print("=" * 70)
    subset = df[df['familia'] == familia.upper()]
    print(f"Total: {len(subset)}\n")
    for _, row in subset.head(limit).iterrows():
        code = str(row.get('Material', ''))[:12]
        desc = str(row.get('Material Description', ''))[:70]
        unit = str(row.get('BUn', ''))[:5]
        print(f"  {code:12} | {unit:4} | {desc}")
    if len(subset) > limit:
        print(f"\n  ... y {len(subset) - limit} más")
    print()


def show_random_sample(df: pd.DataFrame, n: int):
    print("=" * 70)
    print(f"MUESTRA ALEATORIA DE {n} MATERIALES CLASIFICADOS")
    print("=" * 70)
    sample = df.sample(min(n, len(df)), random_state=42)
    for _, row in sample.iterrows():
        code = str(row.get('Material', ''))[:12]
        desc = str(row.get('Material Description', ''))[:55]
        unit = str(row.get('BUn', ''))[:5]
        fam = str(row.get('familia', ''))
        print(f"  [{fam:10}] {code:12} | {unit:4} | {desc}")
    print()


# ---------------------------------------------------------------------------
# Preparación + subida a S3
# ---------------------------------------------------------------------------

def round_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Redondea las columnas numéricas para que el Excel no muestre
    valores con muchos decimales (ej: 0.00292397660818707)."""
    out = df.copy()
    for col, decimals in NUMERIC_COLUMNS_ROUNDING.items():
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors='coerce').round(decimals)
    return out


def upload_classified(df: pd.DataFrame) -> str:
    """Sube a S3 con nombre versionado por fecha."""
    to_save = df.drop(columns=['_rule_index'], errors='ignore')
    to_save = round_numeric_columns(to_save)

    key = build_dated_key(S3_OUTPUT_PREFIX, 'sap_clasificado')
    bucket = get_bucket()
    print(f"Subiendo {len(to_save):,} filas a s3://{bucket}/{key}...")
    upload_dataframe_as_excel(to_save, key)
    print(f"✅ Subido: s3://{bucket}/{key}")
    return key


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    df = load_sap()
    config = load_rules()
    rules = config.get('rules', [])
    classified = classify_dataframe(df, config)

    if '--familia' in sys.argv:
        idx = sys.argv.index('--familia')
        if idx + 1 >= len(sys.argv):
            print("Uso: --familia <NOMBRE>")
            sys.exit(1)
        show_only_familia(classified, sys.argv[idx + 1])
        return

    if '--sample' in sys.argv:
        idx = sys.argv.index('--sample')
        n = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 30
        show_random_sample(classified, n)
        return

    print_distribution(classified)
    print_rule_usage(classified, rules)
    show_samples_per_familia(classified, n=5)

    if '--upload' in sys.argv:
        upload_classified(classified)


if __name__ == '__main__':
    main()
