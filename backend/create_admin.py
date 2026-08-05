"""
One-shot script: create or reset the admin user on the live DB.
Run via: fly ssh console -a qwantej -C "cd /app && python create_admin.py"
"""
import asyncio
import sys
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, init_db
from app.core.auth import hash_password
from app.models.user import User

EMAIL = "cmhango@gmail.com"
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else None


async def main():
    if not PASSWORD:
        print("Usage: python create_admin.py <password>")
        sys.exit(1)

    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == EMAIL))
        user = result.scalar_one_or_none()

        if user:
            user.hashed_password = hash_password(PASSWORD)
            user.is_active = True
            user.is_admin = True
            action = "updated"
        else:
            user = User(
                email=EMAIL,
                hashed_password=hash_password(PASSWORD),
                name="Cromwell",
                tier="pro",
                subscription_status="active",
                is_admin=True,
            )
            db.add(user)
            action = "created"

        await db.commit()
        await db.refresh(user)
        print(f"User {action}: id={user.id} email={user.email} admin={user.is_admin} tier={user.tier}")


asyncio.run(main())
