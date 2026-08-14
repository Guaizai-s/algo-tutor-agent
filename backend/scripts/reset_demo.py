"""Reset the isolated presentation account to a deterministic learning state.

Run from the repository root:

    powershell -ExecutionPolicy Bypass -File scripts/reset-demo.ps1
"""

from __future__ import annotations

import asyncio

from app.core.database import async_session_maker
from app.services.demo import DEMO_EMAIL, DEMO_PASSWORD, reset_demo_account


async def main() -> None:
    async with async_session_maker() as session:
        async with session.begin():
            user = await reset_demo_account(session)
    print("Golden demo account reset complete.")
    print(f"  user_id: {user.id}")
    print(f"  login:   {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
