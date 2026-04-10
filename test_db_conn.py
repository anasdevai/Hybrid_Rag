import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

async def test_conn():
    user = os.getenv("POSTGRES_USER", "postgres")
    pw = os.getenv("POSTGRES_PASSWORD", "admin123")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "qdrant")
    
    url = f"postgresql+asyncpg://{user}:{pw}@{host}:{port}/{db}"
    print(f"Testing connection to: {url}")
    
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute("SELECT 1")
            print("Successfully connected to the database!")
    except Exception as e:
        print(f"Failed to connect: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_conn())
