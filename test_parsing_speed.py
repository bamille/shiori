#!/usr/bin/env python3
"""Test streaming JSON parsing for performance."""

from pathlib import Path
from zipfile import ZipFile
import json
import time

jitendex_path = Path("data/jitendex-yomitan.zip")

if jitendex_path.exists():
    print("Testing parsing strategies...")
    
    with ZipFile(jitendex_path, "r") as zf:
        # Find a large bank file
        term_banks = sorted([f for f in zf.namelist() 
                            if f.startswith("term_bank_") and f.endswith(".json")])
        
        # Test with a mid-size bank
        test_bank = term_banks[100]  # test bank 100-ish
        
        print(f"\nTesting with {test_bank}:")
        
        # Strategy 1: Load entire file, parse as JSON
        start = time.time()
        data = zf.read(test_bank).decode("utf-8")
        entries = json.loads(data)
        strategy1_time = time.time() - start
        print(f"  Strategy 1 (load + parse): {strategy1_time:.4f}s, {len(entries)} entries")
        
        # Strategy 2: Try ijson if available
        try:
            import ijson
            start = time.time()
            data = zf.read(test_bank)
            count = 0
            for entry in ijson.items(data, "item"):
                count += 1
            strategy2_time = time.time() - start
            print(f"  Strategy 2 (ijson streaming): {strategy2_time:.4f}s, {count} entries")
        except ImportError:
            print(f"  Strategy 2 (ijson) not available")
        
        # Now estimate total time for all 217 banks
        total_entries_estimate = sum(
            len(json.loads(zf.read(f).decode("utf-8")))
            for f in term_banks[:10]  # Sample 10 banks
        ) / 10 * len(term_banks)
        
        estimated_time_s1 = strategy1_time * len(term_banks)
        print(f"\nEstimated time for all {len(term_banks)} banks:")
        print(f"  Strategy 1: {estimated_time_s1:.1f}s (current implementation)")
