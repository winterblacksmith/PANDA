from pathlib import Path
import pandas as pd

DATA_DIR = Path("data")

csv_files = list(DATA_DIR.glob("*.csv"))

tree_csv_files = [
    file for file in csv_files
    if "Final" in file.name and "Column_Headers" not in file.name
]

if not tree_csv_files:
    raise FileNotFoundError("No tree CSV files found in the data folder.")

print("Tree CSV files found:")
for i, file in enumerate(tree_csv_files, start=1):
    print(f"{i}. {file.name}")

csv_path = tree_csv_files[0]
print(f"\nReading tree CSV: {csv_path.name}")

df = pd.read_csv(csv_path, nrows=1000)

print("\nColumns:")
for col in df.columns:
    print(f"- {col}")

print("\nFirst 5 rows:")
print(df.head())

print("\nBasic info:")
print(df.info())