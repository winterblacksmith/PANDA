from pathlib import Path
import pandas as pd

DATA_DIR = Path("data")

csv_files = [
    file for file in DATA_DIR.glob("*.csv")
    if "Final" in file.name and "Column_Headers" not in file.name
]

if not csv_files:
    raise FileNotFoundError("No tree CSV files found.")

for csv_path in csv_files:
    print("=" * 80)
    print(f"Profiling: {csv_path.name}")

    df = pd.read_csv(csv_path)

    print(f"\nRows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")

    print("\nNon-empty values per column:")
    non_null_counts = df.notna().sum().sort_values(ascending=False)
    print(non_null_counts)

    print("\nImportant column checks:")

    important_cols = [
        "common_name",
        "scientific_name",
        "state",
        "native",
        "diameter_breast_height_binned_CM",
        "diameter_breast_height_CM",
        "longitude_coordinate",
        "latitude_coordinate",
        "condition",
        "height_M",
        "location_type",
        "zipcode",
        "neighborhood",
    ]

    for col in important_cols:
        if col in df.columns:
            non_empty = df[col].notna().sum()
            print(f"{col}: {non_empty:,} non-empty values")

    if "common_name" in df.columns:
        print("\nTop 10 common names:")
        print(df["common_name"].value_counts(dropna=False).head(10))

    if "native" in df.columns:
        print("\nNative values:")
        print(df["native"].value_counts(dropna=False).head(10))

    if "diameter_breast_height_binned_CM" in df.columns:
        print("\nDiameter bins:")
        print(df["diameter_breast_height_binned_CM"].value_counts(dropna=False).head(20))

    if "condition" in df.columns:
        print("\nCondition values:")
        print(df["condition"].value_counts(dropna=False).head(20))