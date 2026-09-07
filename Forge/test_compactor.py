"""
test_compactor.py - Automated tests for TokenSlayer compaction, expansion, and patching.
"""

import sys
import unittest
from pathlib import Path

# Add Forge to Python path if needed
FORGE_DIR = Path(__file__).parent
if str(FORGE_DIR) not in sys.path:
    sys.path.insert(0, str(FORGE_DIR))

from compactor import Compactor, node_registry
from context_stripper import estimate_tokens


class TestTokenSlayer(unittest.TestCase):
    
    def setUp(self):
        node_registry.clear()
        self.compactor = Compactor()

    def test_bpe_token_estimation(self):
        print("\n--- Test BPE Token Estimation ---")
        text = "def hello_world():\n    print('Hello, world!')"
        
        # Test estimate
        tokens = estimate_tokens(text)
        print(f"  Text: {text!r}")
        print(f"  Estimated tokens: {tokens}")
        self.assertTrue(tokens > 0)

    def test_python_compaction_and_expansion(self):
        print("\n--- Test Python AST Compaction ---")
        python_code = """
import os

class Database:
    def __init__(self, url: str):
        self.url = url
        self.connected = False

    async def connect(self) -> bool:
        \"\"\"Establish connection to DB.\"\"\"
        # Long body lines
        if not self.url:
            raise ValueError("URL required")
        self.connected = True
        print(f"Connected to {self.url}")
        return True

def global_helper(x):
    return x * 2
"""
        # Compact
        compacted = self.compactor.compact(Path("database.py"), python_code)
        print("--- Compacted Python Skeletons ---")
        print(compacted)
        print("----------------------------------")
        
        # Verify placeholders exist
        self.assertIn("# NODE:", compacted)
        self.assertIn("class Database:", compacted)
        self.assertNotIn('raise ValueError("URL required")', compacted)
        
        # Verify node_registry was populated
        self.assertTrue(len(node_registry._registry) >= 2)
        
        # Expand back
        expanded = self.compactor.expand_skeleton(compacted)
        print("--- Expanded Python Code ---")
        print(expanded)
        print("----------------------------")
        
        # Verify original content is fully restored
        self.assertIn('raise ValueError("URL required")', expanded)
        self.assertNotIn("# NODE:", expanded)

    def test_js_ts_compaction_and_expansion(self):
        print("\n--- Test JS/TS Brace-Matching Compaction ---")
        ts_code = """
import { Component } from '@angular/core';

class UserService {
    private users: string[] = [];

    async fetchUsers(role: string): Promise<string[]> {
        const response = await fetch(`/api/users?role=${role}`);
        this.users = await response.json();
        console.log("Fetched users successfully");
        return this.users;
    }

    getUsersCount(): number {
        return this.users.length;
    }
}
"""
        # Compact
        compacted = self.compactor.compact(Path("userService.ts"), ts_code)
        print("--- Compacted TS Skeletons ---")
        print(compacted)
        print("------------------------------")
        
        # Verify placeholder
        self.assertIn("/* NODE:", compacted)
        self.assertNotIn('console.log("Fetched users successfully")', compacted)
        
        # Expand back
        expanded = self.compactor.expand_skeleton(compacted)
        print("--- Expanded TS Code ---")
        print(expanded)
        print("------------------------")
        
        self.assertIn('console.log("Fetched users successfully")', expanded)
        self.assertNotIn("/* NODE:", expanded)

    def test_api_endpoints(self):
        print("\n--- Test FastAPI Compaction/Patching Endpoints ---")
        from fastapi.testclient import TestClient
        from forge_api import app
        
        client = TestClient(app)
        
        # Create a temp file to test
        temp_file = Path("temp_test_file.py")
        temp_file.write_text("""
def calculate_sum(a, b):
    # Some comment
    result = a + b
    print("summing", a, b)
    return result

def helper_method():
    return True
""", encoding="utf-8")
        
        try:
            # 1. Test compaction via POST /compact
            resp = client.post("/edits/compact", json={"file_path": str(temp_file.resolve())})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "compacted_and_staged")
            skeleton = data["skeleton"]
            self.assertIn("# NODE:", skeleton)
            
            # Find the node ID from the skeleton
            import re
            match = re.search(r"# NODE:([a-f0-9]{8})", skeleton)
            self.assertIsNotNone(match)
            node_id = match.group(1)
            
            # 2. Test GET /edits/nodes/{node_id}
            resp_node = client.get(f"/edits/nodes/{node_id}")
            self.assertEqual(resp_node.status_code, 200)
            node_data = resp_node.json()
            self.assertIn("calculate_sum", node_data["node_name"])
            
            # 3. Test patching the node via POST /edits/nodes/patch
            new_node_content = '    print("Optimized sum!")\n    return a + b\n'
            resp_patch = client.post("/edits/nodes/patch", json={
                "node_id": node_id,
                "new_content": new_node_content,
                "description": "Surgically patch sum method"
            })
            self.assertEqual(resp_patch.status_code, 200)
            self.assertEqual(resp_patch.json()["status"], "patched_and_staged")
            
            # 4. Preview changes
            resp_prev = client.get("/edits/preview", params={"file_path": str(temp_file.resolve())})
            self.assertEqual(resp_prev.status_code, 200)
            prev_data = resp_prev.json()
            self.assertIn("diff", prev_data)
            
            # 5. Commit changes
            resp_commit = client.post("/edits/commit", params={"create_backups": False})
            self.assertEqual(resp_commit.status_code, 200)
            self.assertIn(str(temp_file.resolve()), resp_commit.json()["committed"])
            
            # Verify the file on disk was surgically updated
            file_content = temp_file.read_text(encoding="utf-8")
            self.assertIn("Optimized sum!", file_content)
            self.assertNotIn("summing", file_content)
            
        finally:
            if temp_file.exists():
                temp_file.unlink()

    def test_checkpoint_exceptions(self):
        print("\n--- Test Checkpoint Preservation Exceptions ---")
        from context_stripper import ContextStripper
        
        stripper = ContextStripper(preserve_last=2)
        
        # Setup conversation messages
        messages = [
            {"role": "system", "content": "Initial system instructions"},
            {"role": "user", "content": "First direct user prompt [KEEP]"},
            {"role": "user", "content": "[read_file] file_edit_buffer.py output..."}, # Tool output (should be discarded)
            {"role": "assistant", "content": "I am working on it..."},
            {"role": "user", "content": "Second direct user prompt"},
            {"role": "user", "content": "Tool Output: success"}, # Tool output (should be discarded)
            {"role": "assistant", "content": "Done!"}, # Will be in preserved last 2
            {"role": "user", "content": "Thank you!"} # Will be in preserved last 2
        ]
        
        # Apply checkpoint
        stripper.apply_checkpoint("Summary of past context")
        processed = stripper.strip_messages(messages)
        
        # Print processed roles and contents for debug
        print("  Processed message roles:")
        for m in processed:
            print(f"    - {m['role']}: {m['content'][:40]}...")
            
        # Expectations:
        # 1. System prompt preserved (system)
        # 2. First user prompt preserved because of '[KEEP]' or because it's direct user instruction
        # 3. Second user prompt preserved because it's direct user instruction
        # 4. Checkpoint message inserted
        # 5. Last 2 turns preserved: 'Done!', 'Thank you!'
        # 6. Tool outputs ('[read_file] ...' and 'Tool Output: ...') discarded!
        
        roles = [m["role"] for m in processed]
        contents = [m["content"] for m in processed]
        
        # System instructions kept
        self.assertIn("Initial system instructions", contents)
        # Direct user prompts kept
        self.assertIn("First direct user prompt [KEEP]", contents)
        self.assertIn("Second direct user prompt", contents)
        # Tool outputs discarded
        self.assertNotIn("[read_file] file_edit_buffer.py output...", contents)
        self.assertNotIn("Tool Output: success", contents)
        # Last turns kept
        self.assertIn("Done!", contents)
        self.assertIn("Thank you!", contents)
        # Checkpoint inserted
        self.assertTrue(any("[CONVERSATION CHECKPOINT]" in c for c in contents))
        print("  ✓ Checkpoint exceptions work perfectly!")


if __name__ == "__main__":
    unittest.main()
