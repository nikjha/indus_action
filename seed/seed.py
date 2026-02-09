import httpx


async def main():
    async with httpx.AsyncClient() as client:
        for i in range(1, 11):
            await client.post("http://localhost:8002/users", json={"id": i, "name": f"user{i}", "department": "Finance" if i % 2 == 0 else "HR", "experience_years": i, "active_task_count": 0, "location": "DL"})
        await client.post("http://localhost:8003/tasks", json={"id": 1, "title": "Task1", "rules": {"department": "Finance", "min_experience": 4, "max_active_tasks": 5}})

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
