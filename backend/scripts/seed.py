import asyncio
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.db import engine, session_factory
from app.models import Complaint, Status
from app.providers.triage.rules import RuleBasedTriage

REPORTS = [
    ("Water pipe is leaking outside the masjid and the lane is getting flooded", "Block 4, old town"),
    ("Bijli is gone again and the transformer is making a loud sound", "Street 8, Gulshan Colony"),
    ("Garbage has not been collected for three days near the school gate", "School Road, North Quarter"),
    ("There is a deep pothole beside the bus stop and bikes are falling", "Main Bazaar bus stop"),
    ("Streetlight is broken and children cannot safely walk home after maghrib", "Lane 12, Garden Town"),
    ("Sewer water is coming up through the drain after the rain", "House 22, Canal View"),
    ("Burst water main is entering the ground floors of the houses", "Street 12, central market"),
    ("Electric wire is hanging low over the road, please send someone urgently", "Railway Crossing Road"),
    ("Road surface has collapsed near the clinic", "Iqbal Avenue, near clinic"),
    ("Waste bins are overflowing and smell is spreading through the lane", "Block 7, Model Colony"),
    ("No light on the footbridge for the last week", "Footbridge near City Park"),
    ("Water pressure is very low since morning in all houses", "Street 3, River Side"),
    ("Open drain has become dangerous for children", "Al-Noor Street"),
    ("Potholes are hidden under rainwater near the college", "College Road"),
    ("Power pole is leaning toward the homes", "Sector B, Green Town"),
    ("Streetlight flickers all night outside the hospital", "Hospital Road"),
    ("Garbage truck skipped our neighbourhood again", "Street 15, West End"),
    ("A water tanker damaged the road and left a large hole", "Market Link Road"),
    ("Sewage smell is very strong near the public park", "Public Park entrance"),
    ("Electricity meter box is sparking near the shop", "Shop 19, Main Bazaar"),
    ("Road is blocked by broken asphalt and traffic is backing up", "Airport Link Road"),
    ("Drain cover is missing outside the primary school", "Primary School Lane"),
    ("Water is wasting from a public tap since yesterday", "Bus Terminal"),
    ("The street is dark because three lamps stopped working", "Street 6, New Town"),
    ("Garbage is scattered around the market after collection", "Fruit Market"),
    ("Small pothole near our house needs repair", "House 9, Peace Colony"),
    ("Sewer line appears blocked and dirty water is standing", "Street 2, East Quarter"),
    ("Transformer outage has left the whole lane without power", "Lane 5, Workers Colony"),
    ("Broken footpath is forcing people onto the busy road", "Library Road"),
    ("Water leak is making the entrance slippery", "Community Centre"),
]


async def seed() -> None:
    provider = RuleBasedTriage()
    async with session_factory() as session:
        for text, location in REPORTS:
            complaint_id = uuid5(NAMESPACE_URL, f"civicpulse:{text}:{location}")
            exists = await session.scalar(select(Complaint.id).where(Complaint.id == complaint_id))
            if exists:
                continue
            result = await provider.triage(text, location)
            now = datetime.now(UTC)
            session.add(
                Complaint(
                    id=complaint_id,
                    text=text,
                    location=location,
                    category=result.category,
                    priority=result.priority,
                    status=Status.OPEN,
                    ai_summary=result.summary,
                    triaged_by="rules:seed",
                    triage_latency_ms=0,
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.commit()
    await engine.dispose()
    print(f"Seeded {len(REPORTS)} deterministic complaints (existing rows were preserved).")


if __name__ == "__main__":
    asyncio.run(seed())
