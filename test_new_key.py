import os
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

async def test_key():
    key = os.getenv("GOOGLE_API_KEY")
    print(f"Testing Key: {key[:10]}...")
    
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=key)
    try:
        res = await llm.ainvoke("Hi, are you working?")
        print("Success! Response:", res.content)
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    asyncio.run(test_key())
