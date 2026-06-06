"""
DeadlineBot - Telegram Bot untuk Pengingat Deadline Tim
Tanpa API berbayar — prioritas dihitung otomatis berdasarkan deadline & prioritas
"""

import os
import asyncio
import logging
from datetime import datetime, date, time as dtime
import pytz
from dotenv import load_dotenv

load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from supabase import create_client, Client

# ─── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL   = os.getenv("SUPABASE_URL")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY")
TIMEZONE       = os.getenv("TIMEZONE", "Asia/Jakarta")

TZ = pytz.timezone(TIMEZONE)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ConversationHandler states
WAITING_TITLE, WAITING_DEADLINE, WAITING_ASSIGNEE, WAITING_PRIORITY = range(4)

# ─── HELPERS ───────────────────────────────────────────────────────────────────

def now_jakarta() -> datetime:
    return datetime.now(TZ)

def days_until(deadline_str: str) -> int:
    deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
    return (deadline - date.today()).days

def urgency_emoji(days: int) -> str:
    if days < 0:   return "🔴 TERLAMBAT"
    if days == 0:  return "🚨 HARI INI"
    if days == 1:  return "⚠️ BESOK"
    if days <= 3:  return "🟠 Segera"
    if days <= 7:  return "🟡 Minggu ini"
    return "🟢 Masih aman"

def format_task(task: dict) -> str:
    days = days_until(task["deadline"])
    status = urgency_emoji(days)
    assignee = task.get("assignee") or "Semua"
    priority_map = {"high": "🔥 Tinggi", "medium": "🔶 Sedang", "low": "🔷 Rendah"}
    priority = priority_map.get(task.get("priority", "medium"), "🔶 Sedang")
    return (
        f"📌 *{task['title']}*\n"
        f"   📅 Deadline: `{task['deadline']}` ({days} hari lagi)\n"
        f"   {status}\n"
        f"   👤 Assignee: {assignee}\n"
        f"   {priority}\n"
        f"   🆔 ID: `{task['id']}`"
    )

def prioritas_lokal(tasks: list) -> str:
    """Analisis prioritas tanpa API berbayar — logika berdasarkan deadline & prioritas."""
    if not tasks:
        return "Tidak ada tugas aktif saat ini."

    priority_score = {"high": 0, "medium": 10, "low": 20}

    def skor(t):
        days = days_until(t["deadline"])
        return days + priority_score.get(t.get("priority", "medium"), 10)

    sorted_tasks = sorted(tasks, key=skor)

    overdue   = [t for t in tasks if days_until(t["deadline"]) < 0]
    critical  = [t for t in tasks if 0 <= days_until(t["deadline"]) <= 3]
    this_week = [t for t in tasks if 4 <= days_until(t["deadline"]) <= 7]

    lines = []

    # Status kondisi tim
    if overdue:
        lines.append(f"🚨 *PERINGATAN:* Ada *{len(overdue)} tugas terlambat!* Segera tindak lanjuti.\n")
    elif critical:
        lines.append(f"⚠️ *Kondisi Tim:* {len(critical)} tugas butuh perhatian segera (≤3 hari).\n")
    else:
        lines.append(f"✅ *Kondisi Tim:* Aman. Tidak ada deadline mendesak.\n")

    # Urutan prioritas
    lines.append("📊 *Urutan Prioritas Sekarang:*")
    for i, t in enumerate(sorted_tasks[:7], 1):
        days = days_until(t["deadline"])
        emoji = urgency_emoji(days)
        lines.append(f"  {i}. {t['title']} — {emoji} ({t['deadline']})")

    # Saran hari ini
    lines.append("")
    if overdue:
        top = overdue[0]
        lines.append(f"💡 *Saran:* Fokus selesaikan *\"{top['title']}\"* yang sudah melewati deadline.")
    elif sorted_tasks:
        top = sorted_tasks[0]
        lines.append(f"💡 *Saran:* Mulai hari ini dengan *\"{top['title']}\"* — paling mendesak.")

    return "\n".join(lines)

# ─── SUPABASE OPERATIONS ───────────────────────────────────────────────────────

def db_add_task(chat_id, title, deadline, assignee, priority, added_by) -> dict:
    data = {
        "chat_id": str(chat_id),
        "title": title,
        "deadline": deadline,
        "assignee": assignee,
        "priority": priority,
        "added_by": added_by,
        "status": "pending",
        "created_at": now_jakarta().isoformat()
    }
    res = supabase.table("tasks").insert(data).execute()
    return res.data[0] if res.data else {}

def db_get_tasks(chat_id, status="pending") -> list:
    res = (
        supabase.table("tasks")
        .select("*")
        .eq("chat_id", str(chat_id))
        .eq("status", status)
        .order("deadline", desc=False)
        .execute()
    )
    return res.data or []

def db_complete_task(task_id) -> bool:
    res = (
        supabase.table("tasks")
        .update({"status": "done", "completed_at": now_jakarta().isoformat()})
        .eq("id", task_id)
        .execute()
    )
    return bool(res.data)

def db_delete_task(task_id) -> bool:
    res = supabase.table("tasks").delete().eq("id", task_id).execute()
    return bool(res.data)

def db_get_all_chats() -> list:
    res = supabase.table("tasks").select("chat_id").eq("status", "pending").execute()
    if not res.data:
        return []
    return list(set(row["chat_id"] for row in res.data))

# ─── COMMAND HANDLERS ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    text = (
        f"👋 Halo *{name}*! Saya *DeadlineBot* 🤖\n\n"
        "Saya akan membantu tim kamu tidak ketinggalan deadline\\!\n\n"
        "📋 *Perintah tersedia:*\n"
        "• /tambah — Tambah tugas baru\n"
        "• /daftar — Lihat semua tugas aktif\n"
        "• /selesai — Tandai tugas selesai\n"
        "• /hapus — Hapus tugas\n"
        "• /prioritas — Analisis & urutan prioritas\n"
        "• /ringkasan — Ringkasan tim\n"
        "• /bantuan — Panduan lengkap\n\n"
        "💡 *Tips:* Tambahkan saya ke grup tim agar semua bisa lihat bersama\\!"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Panduan DeadlineBot*\n\n"
        "*Tambah Tugas:*\n"
        "`/tambah` → ikuti langkah interaktif\n\n"
        "*Lihat Tugas:*\n"
        "`/daftar` → tugas aktif\n"
        "`/daftar selesai` → tugas selesai\n\n"
        "*Selesaikan/Hapus:*\n"
        "`/selesai <ID>` → tandai selesai\n"
        "`/hapus <ID>` → hapus tugas\n\n"
        "*Analisis:*\n"
        "`/prioritas` → urutan prioritas otomatis\n"
        "`/ringkasan` → statistik tim\n\n"
        "*Format Tanggal:* `YYYY-MM-DD`\n"
        "contoh: `2025-12-31`\n\n"
        "🔔 Pengingat otomatis jam 08:00 WIB\n"
        "untuk deadline H-3, H-1, dan hari-H."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ─── CONVERSATION: TAMBAH TUGAS ────────────────────────────────────────────────

async def cmd_tambah(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "➕ *Tambah Tugas Baru*\n\n"
        "Langkah 1/4 — Ketik *judul tugas*:\n"
        "_(contoh: Buat laporan bulanan)_\n\n"
        "Ketik /batal untuk membatalkan.",
        parse_mode="Markdown"
    )
    return WAITING_TITLE

async def received_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["task_title"] = update.message.text.strip()
    await update.message.reply_text(
        "📅 Langkah 2/4 — Ketik *tanggal deadline*:\n"
        "Format: `YYYY-MM-DD`\n"
        "_(contoh: 2026-07-31)_",
        parse_mode="Markdown"
    )
    return WAITING_DEADLINE

async def received_deadline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text(
            "❌ Format salah! Gunakan `YYYY-MM-DD`\n_(contoh: 2026-07-31)_",
            parse_mode="Markdown"
        )
        return WAITING_DEADLINE
    ctx.user_data["task_deadline"] = raw
    await update.message.reply_text(
        "👤 Langkah 3/4 — Siapa yang bertanggung jawab?\n"
        "_(Ketik nama, atau `semua` untuk seluruh tim)_",
        parse_mode="Markdown"
    )
    return WAITING_ASSIGNEE

async def received_assignee(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["task_assignee"] = update.message.text.strip()
    keyboard = [[
        InlineKeyboardButton("🔥 Tinggi",  callback_data="priority_high"),
        InlineKeyboardButton("🔶 Sedang",  callback_data="priority_medium"),
        InlineKeyboardButton("🔷 Rendah",  callback_data="priority_low"),
    ]]
    await update.message.reply_text(
        "⚡ Langkah 4/4 — Pilih *prioritas* tugas:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return WAITING_PRIORITY

async def received_priority(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    priority = query.data.replace("priority_", "")
    user = query.from_user
    chat_id = query.message.chat_id

    task = db_add_task(
        chat_id=chat_id,
        title=ctx.user_data["task_title"],
        deadline=ctx.user_data["task_deadline"],
        assignee=ctx.user_data["task_assignee"],
        priority=priority,
        added_by=user.first_name or user.username or str(user.id)
    )
    await query.edit_message_text(
        f"✅ *Tugas berhasil ditambahkan!*\n\n{format_task(task)}",
        parse_mode="Markdown"
    )
    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel_conversation(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Dibatalkan.")
    return ConversationHandler.END

# ─── DAFTAR / SELESAI / HAPUS ──────────────────────────────────────────────────

async def cmd_daftar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    status = "done" if args and args[0].lower() == "selesai" else "pending"
    chat_id = update.effective_chat.id
    tasks = db_get_tasks(chat_id, status)
    label = "✅ Selesai" if status == "done" else "📋 Aktif"

    if not tasks:
        msg = "Tidak ada tugas aktif saat ini." if status == "pending" else "Belum ada tugas yang diselesaikan."
        await update.message.reply_text(msg)
        return

    header = f"*{label} — {len(tasks)} Tugas*\n{'─' * 28}\n\n"
    body = "\n\n".join(format_task(t) for t in tasks)
    full = header + body
    if len(full) > 4000:
        full = full[:4000] + "\n\n_...dan lainnya_"
    await update.message.reply_text(full, parse_mode="Markdown")

async def cmd_selesai(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Gunakan: `/selesai <ID>`\n_ID ada di /daftar_", parse_mode="Markdown")
        return
    task_id = ctx.args[0].strip()
    if db_complete_task(task_id):
        await update.message.reply_text(f"✅ Tugas selesai! 🎉", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ ID `{task_id}` tidak ditemukan.", parse_mode="Markdown")

async def cmd_hapus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Gunakan: `/hapus <ID>`\n_ID ada di /daftar_", parse_mode="Markdown")
        return
    task_id = ctx.args[0].strip()
    if db_delete_task(task_id):
        await update.message.reply_text(f"🗑️ Tugas berhasil dihapus.")
    else:
        await update.message.reply_text(f"❌ ID `{task_id}` tidak ditemukan.", parse_mode="Markdown")

# ─── PRIORITAS & RINGKASAN ─────────────────────────────────────────────────────

async def cmd_prioritas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tasks = db_get_tasks(chat_id)
    result = prioritas_lokal(tasks)
    await update.message.reply_text(
        f"📋 *Analisis Prioritas Tim*\n{'─'*28}\n\n{result}",
        parse_mode="Markdown"
    )

async def cmd_ringkasan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tasks = db_get_tasks(chat_id)

    if not tasks:
        await update.message.reply_text("📭 Tidak ada tugas aktif saat ini.")
        return

    overdue   = [t for t in tasks if days_until(t["deadline"]) < 0]
    today_t   = [t for t in tasks if days_until(t["deadline"]) == 0]
    this_week = [t for t in tasks if 1 <= days_until(t["deadline"]) <= 7]
    upcoming  = [t for t in tasks if days_until(t["deadline"]) > 7]
    high_prio = [t for t in tasks if t.get("priority") == "high"]

    lines = [f"📊 *Ringkasan Tugas Tim*\n{'─'*28}\n"]
    lines.append(f"📌 Total aktif: *{len(tasks)}* tugas")
    lines.append(f"🔴 Terlambat: *{len(overdue)}*")
    lines.append(f"🚨 Hari ini: *{len(today_t)}*")
    lines.append(f"🟠 Minggu ini: *{len(this_week)}*")
    lines.append(f"🟢 Ke depan: *{len(upcoming)}*")
    lines.append(f"🔥 Prioritas Tinggi: *{len(high_prio)}*")

    if overdue:
        lines.append(f"\n⚠️ *TERLAMBAT:*")
        for t in overdue[:3]:
            lines.append(f"  • {t['title']} ({t['deadline']})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── SCHEDULER: PENGINGAT OTOMATIS ────────────────────────────────────────────

async def jadwal_harian(ctx: ContextTypes.DEFAULT_TYPE):
    chat_ids = db_get_all_chats()
    for chat_id in chat_ids:
        tasks = db_get_tasks(int(chat_id))
        urgent = [t for t in tasks if days_until(t["deadline"]) in (-1, 0, 1, 3)]
        if not urgent:
            continue
        lines = ["🔔 *Pengingat Deadline Hari Ini*\n"]
        for t in urgent:
            lines.append(format_task(t))
            lines.append("")
        lines.append("_Gunakan /daftar untuk lihat semua tugas._")
        try:
            await ctx.bot.send_message(
                chat_id=int(chat_id),
                text="\n".join(lines),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Gagal kirim ke {chat_id}: {e}")

# ─── MAIN ──────────────────────────────────────────────────────────────────────

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("tambah", cmd_tambah)],
        states={
            WAITING_TITLE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, received_title)],
            WAITING_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_deadline)],
            WAITING_ASSIGNEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_assignee)],
            WAITING_PRIORITY: [CallbackQueryHandler(received_priority, pattern="^priority_")],
        },
        fallbacks=[CommandHandler("batal", cancel_conversation)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("bantuan",   cmd_help))
    app.add_handler(CommandHandler("daftar",    cmd_daftar))
    app.add_handler(CommandHandler("selesai",   cmd_selesai))
    app.add_handler(CommandHandler("hapus",     cmd_hapus))
    app.add_handler(CommandHandler("prioritas", cmd_prioritas))
    app.add_handler(CommandHandler("ringkasan", cmd_ringkasan))
    app.add_handler(conv)

    # Pengingat otomatis jam 08:00 WIB
    jam_08 = dtime(hour=8, minute=0, tzinfo=TZ)
    app.job_queue.run_daily(jadwal_harian, time=jam_08, name="pengingat_harian")

    logger.info("🚀 DeadlineBot berjalan!")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    # Jaga bot tetap berjalan
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
