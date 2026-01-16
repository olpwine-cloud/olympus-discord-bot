import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import sqlite3
import asyncio
import qrcode
import os
from openpyxl import Workbook

import os
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATABASE
# =========================
db = sqlite3.connect("gigibot.db")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer TEXT,
    services TEXT,
    price INTEGER,
    start TEXT,
    end TEXT,
    room TEXT,
    status TEXT,
    strike INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS vip (
    user TEXT,
    tier TEXT,
    start TEXT,
    end TEXT,
    streak INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS feedback (
    customer TEXT,
    rating INTEGER,
    review TEXT
)
""")

db.commit()

# =========================
# CONFIG
# =========================
SERVICES = {
    "Host 60 นาที": {"price": 2800, "duration": 60, "room": True},
    "Host 90 นาที": {"price": 4200, "duration": 90, "room": True},
    "ดูดวง": {"price": 999, "duration": 30, "room": False},
    "ที่ปรึกษา": {"price": 1200, "duration": 30, "room": False},
    "Drink Shot": {"price": 300, "duration": 0, "room": False},
    "ถ่ายภาพ": {"price": 1500, "duration": 30, "room": False},
}

ROOMS = [
    "the divine mirror room",
    "heaven lounge room",
    "velvet cage room",
    "the abyss room",
    "The Golden Pantheon",
    "Chamber sin"
]

VIP_TIERS = {
    "VIP1": 0.9,
    "VIP2": 0.8,
    "VIP3": 0.7
}

# =========================
# UTILS
# =========================
def calc_end(start, services):
    total = sum(SERVICES[s]["duration"] for s in services)
    return start + timedelta(minutes=total)

def room_available(room, start, end):
    cur.execute("SELECT start, end FROM bills WHERE room=?", (room,))
    for s, e in cur.fetchall():
        if start < datetime.fromisoformat(e) and end > datetime.fromisoformat(s):
            return False
    return True

# =========================
# UI : OPEN BILL
# =========================
class OpenBillModal(discord.ui.Modal, title="🧾 เปิดบิลใหม่"):
    customer = discord.ui.TextInput(label="ชื่อลูกค้า")
    services = discord.ui.TextInput(
        label="บริการ (คั่นด้วย ,)",
        placeholder="Host 60 นาที, ถ่ายภาพ"
    )
    start_time = discord.ui.TextInput(
        label="เวลาเริ่ม (HH:MM)",
        placeholder="20:00"
    )

    async def on_submit(self, interaction: discord.Interaction):
        svs = [s.strip() for s in self.services.value.split(",")]
        start = datetime.combine(datetime.now().date(),
                                 datetime.strptime(self.start_time.value, "%H:%M").time())
        end = calc_end(start, svs)

        price = sum(SERVICES[s]["price"] for s in svs)

        await interaction.response.send_message(
            f"⏰ เริ่ม {start.strftime('%H:%M')} | จบ {end.strftime('%H:%M')}\n"
            f"💸 ยอดรวม {price:,} บาท\n"
            f"เลือกห้องต่อเลยค่ะ Reception 💅",
            view=RoomView(self.customer.value, svs, start, end, price),
            ephemeral=True
        )

# =========================
# ROOM VIEW
# =========================
class RoomView(discord.ui.View):
    def __init__(self, customer, services, start, end, price):
        super().__init__()
        self.customer = customer
        self.services = services
        self.start = start
        self.end = end
        self.price = price

        for r in ROOMS:
            if room_available(r, start, end):
                self.add_item(RoomButton(r, self))

class RoomButton(discord.ui.Button):
    def __init__(self, room, parent):
        super().__init__(label=room, style=discord.ButtonStyle.primary)
        self.room = room
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        cur.execute("""
        INSERT INTO bills (customer, services, price, start, end, room, status)
        VALUES (?,?,?,?,?,?,?)
        """, (
            self.parent.customer,
            ",".join(self.parent.services),
            self.parent.price,
            self.parent.start.isoformat(),
            self.parent.end.isoformat(),
            self.room,
            "WAIT_PAYMENT"
        ))
        db.commit()

        bill_id = cur.lastrowid

        await interaction.response.send_message(
            f"🏨 ห้อง **{self.room}** จองแล้วค่ะ\n"
            f"💳 กำลังส่ง QR ให้ลูกค้าเลยนะคะ 😌",
            ephemeral=True
        )

        await send_payment_flow(interaction.user, bill_id, self.parent.price)

# =========================
# PAYMENT FLOW
# =========================
async def send_payment_flow(user, bill_id, amount):
    qr = qrcode.make(f"PAYMENT|BILL:{bill_id}|AMOUNT:{amount}")
    qr_path = f"qr_{bill_id}.png"
    qr.save(qr_path)

    await user.send(
        f"💸 บิล #{bill_id}\n"
        f"ยอด {amount:,} บาท\n"
        f"กรุณาชำระภายใน 5 นาที แล้วส่งสลิปค่ะ 💅",
        file=discord.File(qr_path)
    )

    os.remove(qr_path)

    await asyncio.sleep(300)

    cur.execute("SELECT status FROM bills WHERE id=?", (bill_id,))
    if cur.fetchone()[0] == "WAIT_PAYMENT":
        cur.execute("""
        UPDATE bills SET status='CANCELLED', strike=strike+1 WHERE id=?
        """, (bill_id,))
        db.commit()

# =========================
# COMMAND
# =========================
@bot.command()
@commands.has_role("Reception")
async def openbill(ctx):
    await ctx.send_modal(OpenBillModal())

@bot.command()
@commands.has_role("Reception")
async def export(ctx):
    wb = Workbook()
    ws = wb.active
    ws.append(["Customer", "Services", "Price", "Start", "End", "Room", "Status"])

    cur.execute("SELECT customer, services, price, start, end, room, status FROM bills")
    for row in cur.fetchall():
        ws.append(row)

    wb.save("report.xlsx")
    await ctx.send("📊 Export เรียบร้อยค่ะ Reception 💅", file=discord.File("report.xlsx"))

# =========================
# RUN
# =========================
bot.run(TOKEN)
