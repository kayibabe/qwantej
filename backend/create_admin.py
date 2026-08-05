"""
Create or reset an admin user on the database.
Usage: python create_admin.py <email> <password>
Run on Fly.io: fly ssh console -a qwantej -C "cd /app && python create_admin.py <email> <password>"
"""
import asyncio
import sys
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, init_db
from app.core.auth import hash_password
from app.models.user import User


async def main(email: str, password: str):
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            user.hashed_password = hash_password(password)
            user.is_active = True
            user.is_admin = True
            action = "updated"
        else:
            name = email.split("@")[0]
            user = User(
                email=email,
                hashed_password=hash_password(password),
                name=name,
                tier="pro",
                subscription_status="active",
                is_admin=True,
            )
            db.add(user)
            action = "created"

        await db.commit()
        await db.refresh(user)
        print(f"User {action}: id={user.id} email={user.email} admin={user.is_admin} tier={user.tier}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python create_admin.py <email> <password>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
