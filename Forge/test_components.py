"""
Test script for the new Forge components.
Run this to verify mesh_bus, checkpoint_engine, and memory_vault work together.
"""

import asyncio
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

from mesh_bus import mesh_bus, MeshEvent
from checkpoint_engine import checkpoint_engine
from memory_vault import memory_vault


async def test_mesh_bus():
    print("\n=== Testing MeshBus ===")
    
    events_received = []
    
    def handler(event: MeshEvent):
        events_received.append(event.type)
        print(f"  Received: {event.type}")
    
    mesh_bus.subscribe("test_event", handler)
    mesh_bus.publish_simple("test_event", {"message": "Hello"}, "test-session")
    
    await asyncio.sleep(0.1)  # Let async dispatch complete
    
    assert len(events_received) == 1, f"Expected 1 event, got {len(events_received)}"
    print(f"  Stats: {mesh_bus.get_stats()}")
    print("  ✓ MeshBus works!")


async def test_checkpoint_engine():
    print("\n=== Testing CheckpointEngine ===")
    
    await checkpoint_engine.start()
    
    # Monitor a session
    await checkpoint_engine.monitor_session("test-session-1", threshold=100)
    
    # Report token counts
    await checkpoint_engine.report_token_count("test-session-1", 50)   # Below threshold
    await checkpoint_engine.report_token_count("test-session-1", 150)  # Above threshold
    
    await asyncio.sleep(0.1)
    
    state = checkpoint_engine.get_session_state("test-session-1")
    assert state is not None, "Session should exist"
    print(f"  Session state: current={state.current_tokens}, threshold={state.threshold}")
    
    await checkpoint_engine.stop()
    print("  ✓ CheckpointEngine works!")


async def test_memory_vault():
    print("\n=== Testing MemoryVault ===")
    
    # Store some entries
    memory_vault.record_file_edit("session-1", "test.py", "Fixed bug in test.py")
    memory_vault.record_decision("session-1", "Use async/await", "Better for I/O bound tasks")
    
    await asyncio.sleep(0.1)
    
    # Query
    results = memory_vault.query(entry_type="file_edit", limit=5)
    assert len(results) >= 1, "Should have file_edit entries"
    print(f"  Found {len(results)} entries")
    
    # Get context
    context = memory_vault.get_session_context("session-2", limit=2)
    print(f"  Context preview: {context[:100]}...")
    
    print("  ✓ MemoryVault works!")


async def test_integration():
    print("\n=== Testing Integration ===")
    
    # Start everything
    await checkpoint_engine.start()
    
    # Simulate a session
    session_id = "demo-session"
    
    # 1. Session starts
    mesh_bus.publish_simple("session_started", {"model": "deepseek-v4-pro"}, session_id)
    await asyncio.sleep(0.05)
    
    # 2. Token count grows
    await checkpoint_engine.monitor_session(session_id, threshold=50)
    await checkpoint_engine.report_token_count(session_id, 80)
    await asyncio.sleep(0.05)
    
    # 3. Checkpoint created
    mesh_bus.publish_simple("checkpoint_created", {
        "summary_length": 500,
        "tokens_before": 80,
        "tokens_after": 30
    }, session_id)
    await asyncio.sleep(0.05)
    
    # 4. Session ends
    mesh_bus.publish_simple("session_ended", {}, session_id)
    await asyncio.sleep(0.05)
    
    # Check vault has entries
    entries = memory_vault.query(limit=10)
    print(f"  Vault has {len(entries)} entries")
    
    await checkpoint_engine.stop()
    print("  ✓ Integration works!")


async def main():
    print("=" * 50)
    print("Forge Components Test Suite")
    print("=" * 50)
    
    try:
        await test_mesh_bus()
        await test_checkpoint_engine()
        await test_memory_vault()
        await test_integration()
        
        print("\n" + "=" * 50)
        print("All tests passed! Components are ready.")
        print("=" * 50)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
