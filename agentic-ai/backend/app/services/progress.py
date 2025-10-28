# app/services/progress.py
import asyncio, time
from typing import Dict, Any, Optional

class ProgressBroker:
    def __init__(self):
        self.queues: Dict[str, asyncio.Queue] = {}
        self.ttl: Dict[str, float] = {}
        self.ttl_seconds = 300  # 5 minutes

    def get_queue(self, request_id: str) -> asyncio.Queue:
        q = self.queues.get(request_id)
        if not q:
            q = asyncio.Queue()
            self.queues[request_id] = q
        self.ttl[request_id] = time.time() + self.ttl_seconds
        return q

    async def publish(self, request_id: str, event: Dict[str, Any]):
        if not request_id:
            return
        q = self.get_queue(request_id)
        await q.put(event)

    def close(self, request_id: str):
        self.queues.pop(request_id, None)
        self.ttl.pop(request_id, None)

    async def gc_loop(self):
        while True:
            await asyncio.sleep(60)
            now = time.time()
            for rid, expires in list(self.ttl.items()):
                if expires < now:
                    self.close(rid)

broker = ProgressBroker()
