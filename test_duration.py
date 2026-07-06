import sys
sys.path.insert(0, '/Users/parthagautam/Desktop/dmrc')
import failure_pipeline as fp

# Test that the Duration column exists
failures = fp.load_failures()
print("Columns in failures dataframe:", failures.columns.tolist())
print("'Duration' in columns:", 'Duration' in failures.columns)
if 'Duration' in failures.columns:
    print("Duration column dtype:", failures['Duration'].dtype)
    print("First few values:", failures['Duration'].head().tolist())
else:
    print("ERROR: Duration column not found!")

# Also check that the duration_capped column exists
print("\n'duration_capped' in columns:", 'duration_capped' in failures.columns)
if 'duration_capped' in failures.columns:
    print("duration_capped column dtype:", failures['duration_capped'].dtype)
    print("First few values:", failures['duration_capped'].head().tolist())