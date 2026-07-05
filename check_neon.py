import asyncio
import os

async def check():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    
    url = os.environ['DATABASE_URL']
    url = url.replace('postgresql://', 'postgresql+asyncpg://')
    url = url.replace('?sslmode=require&channel_binding=require', '')
    url = url + '?ssl=require'
    
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        tables = [row[0] for row in r]
        print('Tables in NeonDB:', tables)

asyncio.run(check())