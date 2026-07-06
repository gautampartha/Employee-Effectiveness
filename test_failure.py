import sys
sys.path.insert(0, '/Users/parthagautam/Desktop/dmrc')

import failure_pipeline as fp
import pandas as pd

print("Testing load_failures...")
failures = fp.load_failures()
print(f"Failures shape: {failures.shape}")
print(f"Failures columns: {failures.columns.tolist()}")
print(f"Failures dtypes:\n{failures.dtypes}")
print("\nFirst few rows:")
print(failures.head())

print("\n" + "="*50)
print("Testing load_pm_records...")
pm = fp.load_pm_records()
print(f"PM shape: {pm.shape}")
print(f"PM columns: {pm.columns.tolist()}")
print(f"PM dtypes:\n{pm.dtypes}")
print("\nFirst few rows:")
print(pm.head())

print("\n" + "="*50)
print("Testing classify_failures...")
classified = fp.classify_failures(failures, pm)
print(f"Classified shape: {classified.shape}")
print(f"Classified columns: {classified.columns.tolist()}")
print(f"Classified dtypes:\n{classified.dtypes}")
print("\nValue counts of failure_label:")
print(classified['failure_label'].value_counts(dropna=False))
print("\nFirst few rows with failure_label not null:")
print(classified[['failure_label', 'last_pm_compliance']].head())

# Check if any duplicates in index after classification
print(f"\nAny duplicate indices? {classified.index.duplicated().any()}")

print("\n" + "="*50)
print("Testing get_failure_summary...")
summary = fp.get_failure_summary(classified)
print(f"Summary shape: {summary.shape}")
print(f"Summary columns: {summary.columns.tolist()}")
print("\nFirst few rows of summary:")
print(summary.head())

print("\nDone.")