import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Mind.Monetizing.coinex_integration import CoinExConfig, CoinExV2Client
from Mind.Monetizing.security import SecureStorage


async def main():
    storage = SecureStorage(Path("Data/monetizing/storage"))
    key = storage.get_api_key("coinex_key")
    secret = storage.get_api_key("coinex_secret")
    if not key or not secret:
        print("No CoinEx keys found!")
        return

    client = CoinExV2Client(CoinExConfig(api_key=key, api_secret=secret))

    async with client:
        markets = await client.get_markets()
        cet_markets = [m for m in markets if "CET" in m]
        print("CET markets found:", cet_markets)


if __name__ == "__main__":
    asyncio.run(main())
