import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import skeletal_memory
from context_stripper import ContextStripper

class TestSkeletalMemory(unittest.TestCase):

    def setUp(self):
        skeletal_memory.clear_memory()

    def test_jaccard_similarity(self):
        # Exact match
        self.assertAlmostEqual(skeletal_memory.jaccard_similarity("transition to python 3.12", "transition to python 3.12"), 1.0)
        # partial match
        self.assertGreater(skeletal_memory.jaccard_similarity("transition to python 3.12", "migrated python to 3.12"), 0.3)
        # no match
        self.assertEqual(skeletal_memory.jaccard_similarity("transition to python 3.12", "weather is warm today"), 0.0)

    @patch('skeletal_memory.recycle_node')
    def test_consolidation_and_verification(self, mock_recycle):
        # 1. Create a node
        turn1 = "user: let's switch to python 3.12\nassistant: sure, I will do that."
        nodes1 = [{"category": "decision", "summary": "migrating the stack to Python 3.12"}]
        
        reinforced = skeletal_memory.consolidate_nodes(nodes1, turn1)
        self.assertEqual(len(reinforced), 1)
        node_id = reinforced[0]
        
        node = skeletal_memory.get_node_by_id(node_id)
        self.assertIsNotNone(node)
        self.assertEqual(node["confidence"], 1)
        self.assertFalse(skeletal_memory.should_prune_turn(turn1)) # confidence is 1, so no pruning
        mock_recycle.assert_not_called()

        # 2. Reinforce the node (confidence goes to 2)
        turn2 = "user: is python 3.12 ready?\nassistant: yes, it compiles cleanly."
        nodes2 = [{"category": "decision", "summary": "completed the transition to Python 3.12"}]
        
        reinforced2 = skeletal_memory.consolidate_nodes(nodes2, turn2)
        self.assertEqual(reinforced2, [node_id])
        
        node = skeletal_memory.get_node_by_id(node_id)
        self.assertEqual(node["confidence"], 2)
        mock_recycle.assert_called_once_with(node)
        
        # 3. Check pruning conditions
        self.assertTrue(skeletal_memory.should_prune_turn(turn1))
        self.assertTrue(skeletal_memory.should_prune_turn(turn2))

    def test_build_index(self):
        nodes = [{"category": "bug", "summary": "fixed index quote nesting error"}]
        skeletal_memory.consolidate_nodes(nodes, "turn text")
        
        index_str = skeletal_memory.build_skeletal_index()
        self.assertIn("[SKELETAL CONTEXT INDEX]", index_str)
        self.assertIn("fixed index quote nesting error", index_str)

    @patch('skeletal_memory.query_local_llm')
    def test_context_stripper_integration(self, mock_query):
        # Mock local model response for extraction
        mock_query.return_value = '[{"category": "decision", "summary": "switch stack to SQLite database"}]'
        
        stripper = ContextStripper(preserve_last=2)
        
        # Simulating conversation
        messages = [
            {"role": "system", "content": "You are Jen."},
            {"role": "user", "content": "let's switch to SQLite database"},
            {"role": "assistant", "content": "I have completed the SQLite configuration."}
        ]
        
        # First call: triggers background extraction task in loop
        # Wait, since extraction is async background task, let's call it synchronously or run loop
        import asyncio
        async def run_async_test():
            task1 = stripper._extract_and_recycle_background(messages)
            if task1:
                await task1
            # Re-mock query to trigger matching consolidation
            mock_query.return_value = '[{"category": "decision", "summary": "migrate to SQLite database"}]'
            
            # Simulate turn 2 reinforcement
            messages_t2 = messages + [
                {"role": "user", "content": "is the database ready?"},
                {"role": "assistant", "content": "yes, uvicorn is running and SQLite is active."}
            ]
            task2 = stripper._extract_and_recycle_background(messages_t2)
            if task2:
                await task2
            
        asyncio.run(run_async_test())
        
        # Confirm that SQLite node was created and is double-verified
        active_nodes = skeletal_memory.get_active_nodes()
        self.assertEqual(len(active_nodes), 1)
        self.assertEqual(active_nodes[0]["confidence"], 2)
        
        # Test pruning: strip_messages should prune the first turn (since confidence is 2)
        messages_t2 = messages + [
            {"role": "user", "content": "is the database ready?"},
            {"role": "assistant", "content": "yes, uvicorn is running and SQLite is active."}
        ]
        stripped = stripper.strip_messages(messages_t2)
        
        # The first turn should be replaced with placeholder
        # Find where placeholders are, avoiding assumption about skeletal index order
        recycled_user_idx = -1
        recycled_assistant_idx = -1
        for idx, msg in enumerate(stripped):
            if msg["content"] == "[recycled context node]":
                recycled_user_idx = idx
            elif msg["content"] == "[recycled details]":
                recycled_assistant_idx = idx
                
        self.assertNotEqual(recycled_user_idx, -1)
        self.assertNotEqual(recycled_assistant_idx, -1)
        self.assertEqual(recycled_assistant_idx, recycled_user_idx + 1)
        
        # Check that the skeletal index is injected
        self.assertTrue(any("[SKELETAL CONTEXT INDEX]" in str(m["content"]) for m in stripped if m["role"] == "system"))

if __name__ == '__main__':
    unittest.main()
