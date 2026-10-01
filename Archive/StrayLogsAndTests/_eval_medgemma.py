import os
import sys
import time

sys.path.insert(0, r"C:\Users\danie\program\LUMAX\Backend\Cognition")
from summarizer_compressor import FALLBACK_MODEL_PATHS, SummarizerCompressor

# MedGemma path (index 4 in FALLBACK_MODEL_PATHS)
medgemma_path = FALLBACK_MODEL_PATHS[4]
print(f"MedGemma path: {medgemma_path}")
print(f"Exists: {os.path.exists(medgemma_path)}")

# Sample code for testing
sample_code = """
import os
import sys
from typing import Optional, List, Dict

class DataProcessor:
    \"\"\"Processes data from various sources.\"\"\"
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.data = []
        self._load_config()
    
    def _load_config(self):
        if self.config_path and os.path.exists(self.config_path):
            with open(self.config_path) as f:
                self.config = json.load(f)
        else:
            self.config = {}
    
    def process(self, items: List[Dict]) -> List[Dict]:
        results = []
        for item in items:
            transformed = self._transform(item)
            validated = self._validate(transformed)
            if validated:
                results.append(validated)
        return results
    
    def _transform(self, item: Dict) -> Dict:
        item_copy = item.copy()
        if 'timestamp' in item_copy:
            item_copy['date'] = item_copy.pop('timestamp')
        return item_copy
    
    def _validate(self, item: Dict) -> Optional[Dict]:
        required = ['id', 'name', 'date']
        for field in required:
            if field not in item:
                return None
        return item

def main():
    processor = DataProcessor()
    data = [{'id': 1, 'name': 'test', 'timestamp': '2024-01-01'}]
    result = processor.process(data)
    print(f'Processed {len(result)} items')

if __name__ == '__main__':
    main()
"""

# Load and test
print("\nLoading MedGemma...")
start = time.time()
compressor = SummarizerCompressor(
    model_path=medgemma_path, n_ctx=8192, n_gpu_layers=-1, verbose=False
)
load_time = time.time() - start
print(f"Load time: {load_time:.2f}s")
print(f"Loaded: {compressor.is_loaded}")

if compressor.is_loaded:
    # Test level 3 (deep skeleton)
    print("\n--- Level 3 (Deep Skeleton) ---")
    start = time.time()
    result = compressor.compress(sample_code, level=3)
    elapsed = time.time() - start
    print(f"Time: {elapsed:.2f}s")
    print(f"Input chars: {len(sample_code)}")
    print(f"Output chars: {len(result)}")
    print(f"Reduction: {(1 - len(result) / len(sample_code)) * 100:.1f}%")
    print(f"Result:\n{result}")

    # Test level 4 (symbol table)
    print("\n--- Level 4 (Symbol Table) ---")
    start = time.time()
    result4 = compressor.compress(sample_code, level=4)
    elapsed4 = time.time() - start
    print(f"Time: {elapsed4:.2f}s")
    print(f"Output chars: {len(result4)}")
    print(f"Reduction: {(1 - len(result4) / len(sample_code)) * 100:.1f}%")
    print(f"Result:\n{result4}")

    # Test level 5 (atomic)
    print("\n--- Level 5 (Atomic) ---")
    start = time.time()
    result5 = compressor.compress(sample_code, level=5)
    elapsed5 = time.time() - start
    print(f"Time: {elapsed5:.2f}s")
    print(f"Output chars: {len(result5)}")
    print(f"Reduction: {(1 - len(result5) / len(sample_code)) * 100:.1f}%")
    print(f"Result:\n{result5}")
else:
    print("Failed to load MedGemma")
