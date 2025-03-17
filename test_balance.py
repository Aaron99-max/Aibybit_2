import asyncio
from src.main import create_bybit_client
from src.services.balance_service import BalanceService

async def test_balance():
    try:
        client = await create_bybit_client()
        balance_service = BalanceService(client)
        result = await balance_service.get_balance()
        print("Balance result:", result)
        await client.exchange.close()
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_balance())
