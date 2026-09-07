import asyncio
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_core import CoinExTradingAgent, AgentConfig, UserWallet, IncomeType
from security import SecureStorage

async def test_real_trading():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("TestTrading")

    # 1. Setup Wallet
    wallet = UserWallet(
        solana_address="YourSolanaAddressHere", # Replace with actual if testing
        coinex_api_key="primary", # Refers to key_id in storage
        total_earnings=0.0
    )

    # 2. Check if we have real keys in storage
    storage = SecureStorage()
    key = storage.get_api_key("coinex_key")
    if not key:
        logger.warning("No CoinEx API Key found in SecureStorage (coinex_key).")
        logger.info("Please use the Web UI or backend/Monetizing/security.py to store keys first.")
        # return

    # 3. Create Agent
    config = AgentConfig(
        agent_id="coinex_pro_01",
        name="CoinEx Pro Trader",
        income_types=[IncomeType.CRYPTO_TRADING],
        risk_tolerance="moderate"
    )
    
    agent = CoinExTradingAgent(config.agent_id, config)
    agent.wallet = wallet

    logger.info(f"--- Starting Agent: {agent.config.name} ---")

    # 4. Search for opportunities (Real markets)
    opps = await agent.search_opportunities()
    logger.info(f"Found {len(opps)} real-world opportunities on CoinEx")

    if opps:
        # 5. Execute first opportunity (Sample)
        target_opp = opps[0]
        from agent_core import AgentSwarmTask
        task = await agent.propose_task(target_opp)
        
        logger.info(f"Executing task: {task.name if hasattr(task, 'name') else target_opp.name}")
        success = await agent.execute_task(task)
        
        if success:
            logger.info("Task execution finished successfully!")
            logger.info(f"Final notes: {task.notes}")
        else:
            logger.error(f"Task execution failed: {task.notes}")

    logger.info("--- Test Complete ---")

if __name__ == "__main__":
    asyncio.run(test_real_trading())
