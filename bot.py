"""
DeadlineBot — Pengingat Deadline + Manajemen Lomba
100% gratis, tanpa API berbayar
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

from feature_lomba import (
    # conversation states
    L_NAMA, L_PENYELENGGARA, L_TEMPAT, L_BIAYA,
    L_HADIAH1, L_HADIAH2, L_HADIAH3, L_LINK, L_TIMELINE, L_CATATAN,
    # handlers
    cmd_tambah_lomba, l_nama, l_penyelenggara, l_tempat, l_biaya,
    l_hadiah1, l_hadiah2, l_hadiah3, l_link, l_timeline, l_catatan,
    cmd_daftar_lomba, cmd_detail_lomba, cmd_hapus_lomba,
    cmd_proposal, cmd_set_institusi, cmd_set_ketua, cmd_set_jabatan,
)

# ─── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL   = os.getenv("SUPABASE_URL")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY")
TIMEZONE       = os.getenv("TIMEZONE", "Asia/Jakarta")

TZ = pytz.timezone(TIMEZONE)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# States conversation tambah tugas
WAITING_TITLE, WAITING_DEADLINE, WAITING_ASSIGNEE, WAITING_PRIORITY = range(4)

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def now_jakarta():
    return datetime.now(TZ)

def days_until(deadline_str: str) -> int:
    return (datetime.strptime(deadline_str, "%Y-%m-%d").date() - date.today()).days

def urgency_emoji(days: int) -> str:
    if days < 0:  return "🔴 TERLAMBAT"
    if days == 0: return "🚨 HARI INI"
    if days == 1: return "⚠️ BESOK"
    if days <= 3: return "🟠 Segera"
    if days <= 7: return "🟡 Minggu ini"
    return "🟢 Masih aman"

def format_task(task: dict) -> str:
    days = days_until(task["deadline"])
    pmap = {"high":"🔥 Tinggi","medium":"🔶 Sedang","low":"🔷 Rendah"}
    return (
        f"📌 *{task['title']}*\n"
        f"   📅 Deadline: `{task['deadline']}` ({days} hari lagi)\n"
        f"   {urgency_emoji(days)}\n"
        f"   👤 {task.get('assignee') or 'Semua'}\n"
        f"   {pmap.get(task.get('priority','medium'),'🔶 Sedang')}\n"
        f"   🆔 `{task['id']}`"
    )

def prioritas_lokal(tasks: list) -> str:
    if not tasks:
        return "Tidak ada tugas aktif saat ini."
    pscr = {"high":0,"medium":10,"low":20}
    ranked = sorted(tasks, key=lambda t: days_until(t["deadline"]) + pscr.get(t.get("priority","medium"),10))
    overdue  = [t for t in tasks if days_until(t["deadline"]) < 0]
    critical = [t for t in tasks if 0 <= days_until(t["deadline"]) <= 3]
    lines = []
    if overdue:
        lines.append(f"🚨 *PERINGATAN:* {len(overdue)} tugas TERLAMBAT!\n")
    elif critical:
        lines.append(f"⚠️ {len(critical)} tugas butuh perhatian segera.\n")
    else:
        lines.append("✅ *Kondisi tim aman.*\n")
    lines.append("📊 *Urutan Prioritas:*")
    for i, t in enumerate(ranked[:7], 1):
        lines.append(f"  {i}. {t['title']} — {urgency_emoji(days_until(t['deadline']))}")
    if ranked:
        lines.append(f"\n💡 Fokus sekarang: *\"{ranked[0]['title']}\"*")
    return "\n".join(lines)

# ─── SUPABASE TUGAS ───────────────────────────────────────────────────────────

def db_add_task(chat_id, title, deadline, assignee, priority, added_by):
    res = supabase.table("tasks").insert({
        "chat_id": str(chat_id), "title": title, "deadline": deadline,
        "assignee": assignee, "priority": priority, "added_by": added_by,
        "status": "pending", "created_at": now_jakarta().isoformat()
    }).execute()
    return res.data[0] if res.data else {}

def db_get_tasks(chat_id, status="pending"):
    return (supabase.table("tasks").select("*")
            .eq("chat_id", str(chat_id)).eq("status", status)
            .order("deadline").execute()).data or []

def db_complete_task(task_id):
    return bool(supabase.table("tasks")
                .update({"status":"done","completed_at":now_jakarta().isoformat()})
                .eq("id", task_id).execute().data)

def db_delete_task(task_id):
    return bool(supabase.table("tasks").delete().eq("id", task_id).execute().data)

def db_get_all_chats():
    res = supabase.table("tasks").select("chat_id").eq("status","pending").execute()
    return list(set(r["chat_id"] for r in (res.data or [])))

# ─── COMMAND HANDLERS ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Halo *{name}*\\! Saya *DeadlineBot* 🤖\n\n"
        "📋 *Perintah Tugas:*\n"
        "/tambah — Tambah tugas baru\n"
        "/daftar — Lihat tugas aktif\n"
        "/selesai — Tandai tugas selesai\n"
        "/hapus — Hapus tugas\n"
        "/prioritas — Analisis prioritas\n"
        "/ringkasan — Statistik tim\n\n"
        "🏆 *Perintah Lomba:*\n"
        "/tambah\\_lomba — Input data lomba baru\n"
        "/daftar\\_lomba — Lihat lomba tersimpan\n"
        "/detail\\_lomba — Detail lengkap lomba\n"
        "/hapus\\_lomba — Hapus data lomba\n"
        "/proposal — Generate proposal Word \\(.docx\\)\n\n"
        "⚙️ *Pengaturan Proposal:*\n"
        "/set\\_institusi · /set\\_ketua · /set\\_jabatan\n\n"
        "/bantuan — Panduan lengkap",
        parse_mode="MarkdownV2"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Panduan Lengkap DeadlineBot*\n\n"
        "*── TUGAS ──*\n"
        "`/tambah` — tambah tugas interaktif\n"
        "`/daftar` — tugas aktif\n"
        "`/daftar selesai` — riwayat selesai\n"
        "`/selesai <ID>` — tandai selesai\n"
        "`/hapus <ID>` — hapus tugas\n"
        "`/prioritas` — urutan prioritas otomatis\n"
        "`/ringkasan` — statistik tim\n\n"
        "*── LOMBA ──*\n"
        "`/tambah_lomba` — input data lomba step\\-by\\-step\n"
        "`/daftar_lomba` — semua lomba tersimpan\n"
        "`/detail_lomba <ID>` — detail lengkap\n"
        "`/hapus_lomba <ID>` — hapus lomba\n"
        "`/proposal <ID>` — generate file proposal \\.docx\n\n"
        "*── PROPOSAL ──*\n"
        "`/set_institusi Nama` — nama organisasi/kampus\n"
        "`/set_ketua Nama` — nama penandatangan\n"
        "`/set_jabatan Jabatan` — jabatan penandatangan\n\n"
        "🔔 Pengingat otomatis jam 08:00 WIB \\(H\\-3, H\\-1, Hari\\-H\\)",
        parse_mode="MarkdownV2"
    )

# ─── CONVERSATION: TAMBAH TUGAS ───────────────────────────────────────────────

async def cmd_tambah(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "➕ *Tambah Tugas Baru*\n\n"
        "Langkah 1/4 — Ketik *judul tugas:*\n"
        "_(contoh: Buat laporan bulanan)_\n\n"
        "Ketik /batal untuk batal.",
        parse_mode="Markdown"
    )
    return WAITING_TITLE

async def received_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["task_title"] = update.message.text.strip()
    await update.message.reply_text(
        "📅 Langkah 2/4 — *Tanggal deadline:*\nFormat: `YYYY-MM-DD`\n_(contoh: 2026-12-31)_",
        parse_mode="Markdown"
    )
    return WAITING_DEADLINE

async def received_deadline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("❌ Format salah\\! Gunakan `YYYY\\-MM\\-DD`", parse_mode="MarkdownV2")
        return WAITING_DEADLINE
    ctx.user_data["task_deadline"] = raw
    await update.message.reply_text(
        "👤 Langkah 3/4 — *Siapa yang bertanggung jawab?*\n_(nama atau `semua`)_",
        parse_mode="Markdown"
    )
    return WAITING_ASSIGNEE

async def received_assignee(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["task_assignee"] = update.message.text.strip()
    kb = [[
        InlineKeyboardButton("🔥 Tinggi",  callback_data="priority_high"),
        InlineKeyboardButton("🔶 Sedang",  callback_data="priority_medium"),
        InlineKeyboardButton("🔷 Rendah",  callback_data="priority_low"),
    ]]
    await update.message.reply_text(
        "⚡ Langkah 4/4 — *Pilih prioritas:*",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )
    return WAITING_PRIORITY

async def received_priority(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task = db_add_task(
        chat_id=query.message.chat_id,
        title=ctx.user_data["task_title"],
        deadline=ctx.user_data["task_deadline"],
        assignee=ctx.user_data["task_assignee"],
        priority=query.data.replace("priority_", ""),
        added_by=query.from_user.first_name or str(query.from_user.id)
    )
    await query.edit_message_text(
        f"✅ *Tugas ditambahkan!*\n\n{format_task(task)}", parse_mode="Markdown"
    )
    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel_conversation(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Dibatalkan.")
    return ConversationHandler.END

# ─── DAFTAR / SELESAI / HAPUS ────────────────────────────────────────────────

async def cmd_daftar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    status = "done" if ctx.args and ctx.args[0].lower() == "selesai" else "pending"
    tasks  = db_get_tasks(update.effective_chat.id, status)
    label  = "✅ Selesai" if status == "done" else "📋 Aktif"
    if not tasks:
        await update.message.reply_text(f"Tidak ada tugas {label} saat ini."); return
    full = f"*{label} — {len(tasks)} Tugas*\n{'─'*28}\n\n" + "\n\n".join(format_task(t) for t in tasks)
    if len(full) > 4000: full = full[:4000] + "\n_...dan lainnya_"
    await update.message.reply_text(full, parse_mode="Markdown")

async def cmd_selesai(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Gunakan: `/selesai <ID>`", parse_mode="Markdown"); return
    if db_complete_task(ctx.args[0]):
        await update.message.reply_text("✅ Tugas selesai! 🎉")
    else:
        await update.message.reply_text(f"❌ ID `{ctx.args[0]}` tidak ditemukan.", parse_mode="Markdown")

async def cmd_hapus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Gunakan: `/hapus <ID>`", parse_mode="Markdown"); return
    if db_delete_task(ctx.args[0]):
        await update.message.reply_text("🗑️ Tugas dihapus.")
    else:
        await update.message.reply_text(f"❌ ID `{ctx.args[0]}` tidak ditemukan.", parse_mode="Markdown")

async def cmd_prioritas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tasks = db_get_tasks(update.effective_chat.id)
    await update.message.reply_text(
        f"📋 *Analisis Prioritas*\n{'─'*28}\n\n{prioritas_lokal(tasks)}",
        parse_mode="Markdown"
    )

async def cmd_ringkasan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tasks = db_get_tasks(update.effective_chat.id)
    if not tasks:
        await update.message.reply_text("📭 Tidak ada tugas aktif."); return
    overdue  = [t for t in tasks if days_until(t["deadline"]) < 0]
    today_t  = [t for t in tasks if days_until(t["deadline"]) == 0]
    week_t   = [t for t in tasks if 1 <= days_until(t["deadline"]) <= 7]
    upcoming = [t for t in tasks if days_until(t["deadline"]) > 7]
    high     = [t for t in tasks if t.get("priority") == "high"]
    lines = [
        f"📊 *Ringkasan Tugas Tim*\n{'─'*28}\n",
        f"📌 Total: *{len(tasks)}*  🔥 Tinggi: *{len(high)}*",
        f"🔴 Terlambat: *{len(overdue)}*  🚨 Hari ini: *{len(today_t)}*",
        f"🟠 Minggu ini: *{len(week_t)}*  🟢 Ke depan: *{len(upcoming)}*",
    ]
    if overdue:
        lines.append("\n⚠️ *Terlambat:*")
        for t in overdue[:3]:
            lines.append(f"  • {t['title']} ({t['deadline']})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── WRAPPER LOMBA (inject supabase) ─────────────────────────────────────────

async def w_daftar_lomba(update, ctx):   await cmd_daftar_lomba(update, ctx, supabase)
async def w_detail_lomba(update, ctx):   await cmd_detail_lomba(update, ctx, supabase)
async def w_hapus_lomba(update, ctx):    await cmd_hapus_lomba(update, ctx, supabase)
async def w_proposal(update, ctx):       await cmd_proposal(update, ctx, supabase)
async def w_catatan(update, ctx):        return await l_catatan(update, ctx, supabase)

# ─── SCHEDULER ────────────────────────────────────────────────────────────────

async def jadwal_harian(ctx: ContextTypes.DEFAULT_TYPE):
    for chat_id in db_get_all_chats():
        tasks  = db_get_tasks(int(chat_id))
        urgent = [t for t in tasks if days_until(t["deadline"]) in (-1, 0, 1, 3)]
        if not urgent: continue
        lines = ["🔔 *Pengingat Deadline Hari Ini*\n"]
        for t in urgent:
            lines.append(format_task(t))
            lines.append("")
        lines.append("_Gunakan /daftar untuk lihat semua._")
        try:
            await ctx.bot.send_message(int(chat_id), "\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Gagal kirim ke {chat_id}: {e}")

# ─── MAIN ─────────────────────────────────────────────────────────────────────

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Conversation: tambah tugas
    conv_tugas = ConversationHandler(
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

    # Conversation: tambah lomba
    conv_lomba = ConversationHandler(
        entry_points=[CommandHandler("tambah_lomba", cmd_tambah_lomba)],
        states={
            L_NAMA:        [MessageHandler(filters.TEXT & ~filters.COMMAND, l_nama)],
            L_PENYELENGGARA:[MessageHandler(filters.TEXT & ~filters.COMMAND, l_penyelenggara)],
            L_TEMPAT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, l_tempat)],
            L_BIAYA:       [MessageHandler(filters.TEXT & ~filters.COMMAND, l_biaya)],
            L_HADIAH1:     [MessageHandler(filters.TEXT & ~filters.COMMAND, l_hadiah1)],
            L_HADIAH2:     [MessageHandler(filters.TEXT & ~filters.COMMAND, l_hadiah2)],
            L_HADIAH3:     [MessageHandler(filters.TEXT & ~filters.COMMAND, l_hadiah3)],
            L_LINK:        [MessageHandler(filters.TEXT & ~filters.COMMAND, l_link)],
            L_TIMELINE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, l_timeline)],
            L_CATATAN:     [MessageHandler(filters.TEXT & ~filters.COMMAND, w_catatan)],
        },
        fallbacks=[CommandHandler("batal", cancel_conversation)],
        per_message=False,
    )

    # Tugas
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("bantuan",    cmd_help))
    app.add_handler(CommandHandler("daftar",     cmd_daftar))
    app.add_handler(CommandHandler("selesai",    cmd_selesai))
    app.add_handler(CommandHandler("hapus",      cmd_hapus))
    app.add_handler(CommandHandler("prioritas",  cmd_prioritas))
    app.add_handler(CommandHandler("ringkasan",  cmd_ringkasan))
    app.add_handler(conv_tugas)

    # Lomba
    app.add_handler(conv_lomba)
    app.add_handler(CommandHandler("daftar_lomba",  w_daftar_lomba))
    app.add_handler(CommandHandler("detail_lomba",  w_detail_lomba))
    app.add_handler(CommandHandler("hapus_lomba",   w_hapus_lomba))
    app.add_handler(CommandHandler("proposal",      w_proposal))

    # Pengaturan proposal
    app.add_handler(CommandHandler("set_institusi", cmd_set_institusi))
    app.add_handler(CommandHandler("set_ketua",     cmd_set_ketua))
    app.add_handler(CommandHandler("set_jabatan",   cmd_set_jabatan))

    # Pengingat harian jam 08:00 WIB
    app.job_queue.run_daily(jadwal_harian, time=dtime(8, 0, tzinfo=TZ), name="pengingat")

    logger.info("🚀 DeadlineBot berjalan!")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
