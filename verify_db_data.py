import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

async def verify_data():
    user = os.getenv("POSTGRES_USER", "postgres")
    pw = os.getenv("POSTGRES_PASSWORD", "admin123")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "qdrant")
    
    url = f"postgresql+asyncpg://{user}:{pw}@{host}:{port}/{db}"
    print(f"Connecting to: {url}")
    
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            # Check Users
            user_count = await conn.execute(text("SELECT count(*) FROM users"))
            print(f"Total Users Registered: {user_count.scalar()}")
            
            # Check Chat Sessions
            session_count = await conn.execute(text("SELECT count(*) FROM chat_sessions"))
            print(f"Total Chat Sessions: {session_count.scalar()}")
            
            # Check Chat Messages
            message_count = await conn.execute(text("SELECT count(*) FROM chat_messages"))
            print(f"Total Chat Messages: {message_count.scalar()}")
            
            # Print recent users
            print("\nRecent Users:")
            users = await conn.execute(text("SELECT username, email, created_at FROM users ORDER BY created_at DESC LIMIT 5"))
            for u in users:
                print(f"- {u.username} ({u.email}) | Created: {u.created_at}")
                
            # Print recent messages summary
            print("\nRecent Messages Summary:")
            msgs = await conn.execute(text("""
                SELECT s.title, m.role, left(m.content, 50) as snippet, m.created_at 
                FROM chat_messages m 
                JOIN chat_sessions s ON m.session_id = s.id 
                ORDER BY m.created_at DESC LIMIT 5
            """))
            for m in msgs:
                print(f"- [{m.role}] in '{m.title}': {m.snippet}... | {m.created_at}")
                
    except Exception as e:
        print(f"Error during verification: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_data())
