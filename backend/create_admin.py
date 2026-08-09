"""One-shot admin user creation/reset. Run then delete. Set ADMIN_EMAIL and ADMIN_PASSWORD env vars."""
import asyncio, os
from app.core.database import AsyncSessionLocal
from app.core.auth import hash_password as get_password_hash
from sqlalchemy import text

EMAIL = os.environ["ADMIN_EMAIL"]
PASSWORD = os.environ["ADMIN_PASSWORD"]

async def main():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("SELECT id, email, is_admin FROM users WHERE email = :e"), {"e": EMAIL})
        user = r.one_or_none()
        if user:
            print(f"User exists: id={user.id} is_admin={user.is_admin}")
            hashed = get_password_hash(PASSWORD)
            await db.execute(text("UPDATE users SET hashed_password=:h, is_admin=1, tier='elite' WHERE email=:e"), {"h": hashed, "e": EMAIL})
            await db.commit()
            print("Password reset and is_admin=1 set")
        else:
            print("User NOT FOUND - listing all users:")
            r2 = await db.execute(text("SELECT email, is_admin FROM users"))
            rows = r2.all()
            if not rows:
                print("NO USERS - creating admin")
                hashed = get_password_hash(PASSWORD)
                await db.execute(text("INSERT INTO users (email,hashed_password,name,tier,is_admin,is_active,subscription_status,created_at) VALUES (:e,:h,'Cromwell','elite',1,1,'active',now())"), {"e": EMAIL, "h": hashed})
                await db.commit()
                print("Admin user created")
            else:
                for row in rows:
                    print(row)

asyncio.run(main())
