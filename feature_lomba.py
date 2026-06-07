"""
FITUR LOMBA — Tanpa API berbayar
Analisis poster: input manual step-by-step via ConversationHandler
Generate proposal: docx via Node.js (gratis)
"""

import os
import re
import json
import subprocess
import tempfile
import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)
TZ = pytz.timezone(os.getenv("TIMEZONE", "Asia/Jakarta"))

# ─── SUPABASE ─────────────────────────────────────────────────────────────────

def db_save_lomba(supabase, chat_id: int, data: dict) -> dict:
    row = {
        "chat_id":      str(chat_id),
        "nama_lomba":   data.get("nama_lomba", ""),
        "penyelenggara":data.get("penyelenggara", ""),
        "timeline":     json.dumps(data.get("timeline", []), ensure_ascii=False),
        "tempat":       data.get("tempat", ""),
        "biaya":        data.get("biaya", ""),
        "hadiah_1":     data.get("hadiah_1", ""),
        "hadiah_2":     data.get("hadiah_2", ""),
        "hadiah_3":     data.get("hadiah_3", ""),
        "link_lomba":   data.get("link_lomba", ""),
        "catatan":      data.get("catatan", ""),
        "created_at":   datetime.now(TZ).isoformat(),
    }
    res = supabase.table("lomba").insert(row).execute()
    return res.data[0] if res.data else {}

def db_get_lomba(supabase, chat_id: int) -> list:
    res = (supabase.table("lomba").select("*")
           .eq("chat_id", str(chat_id))
           .order("created_at", desc=True).execute())
    return res.data or []

def db_get_lomba_by_id(supabase, lomba_id: str) -> dict:
    res = supabase.table("lomba").select("*").eq("id", lomba_id).execute()
    return res.data[0] if res.data else {}

def db_delete_lomba(supabase, lomba_id: str) -> bool:
    return bool(supabase.table("lomba").delete().eq("id", lomba_id).execute().data)

def db_update_lomba(supabase, lomba_id: str, field: str, value) -> bool:
    res = supabase.table("lomba").update({field: value}).eq("id", lomba_id).execute()
    return bool(res.data)

# ─── FORMAT RESUME ────────────────────────────────────────────────────────────

def format_resume_lomba(data: dict) -> str:
    timeline = data.get("timeline", [])
    if isinstance(timeline, str):
        try:    timeline = json.loads(timeline)
        except: timeline = []

    timeline_str = ""
    for t in timeline:
        timeline_str += f"      • {t.get('tahap','')}: {t.get('tanggal','')}\n"
    if not timeline_str:
        timeline_str = "      (Belum diisi)\n"

    return (
        f"🏆 *{data.get('nama_lomba','?')}*\n"
        f"{'─'*32}\n"
        f"🏛️ Penyelenggara: {data.get('penyelenggara') or '-'}\n"
        f"📍 Tempat: {data.get('tempat') or '-'}\n"
        f"💰 Biaya: {data.get('biaya') or '-'}\n\n"
        f"🎖️ *Hadiah:*\n"
        f"   🥇 Juara 1: {data.get('hadiah_1') or '-'}\n"
        f"   🥈 Juara 2: {data.get('hadiah_2') or '-'}\n"
        f"   🥉 Juara 3: {data.get('hadiah_3') or '-'}\n\n"
        f"📅 *Timeline:*\n{timeline_str}"
        f"🔗 Link: {data.get('link_lomba') or '-'}\n"
        f"📝 Catatan: {data.get('catatan') or '-'}\n"
        f"🆔 ID: `{data.get('id','?')}`"
    )

# ─── GENERATE PROPOSAL DOCX ───────────────────────────────────────────────────

def generate_proposal_docx(lomba: dict, output_path: str,
                            institusi: str, ketua: str, jabatan_ketua: str) -> str:
    timeline = lomba.get("timeline", [])
    if isinstance(timeline, str):
        try:    timeline = json.loads(timeline)
        except: timeline = []

    bulan_id = ["","Januari","Februari","Maret","April","Mei","Juni",
                "Juli","Agustus","September","Oktober","November","Desember"]
    now = datetime.now(TZ)
    tanggal_str = f"{now.day} {bulan_id[now.month]} {now.year}"

    def esc(s):
        return str(s or "").replace("\\","\\\\").replace("`","\\`").replace("${","\\${").replace('"','\\"')

    timeline_rows = ""
    for i, t in enumerate(timeline, 1):
        tahap   = esc(t.get("tahap",""))
        tanggal = esc(t.get("tanggal",""))
        mode    = "Daring"
        if any(k in tahap.lower() for k in ["final","luring","offline","awarding"]):
            mode = "Luring"
        timeline_rows += f"""
      new TableRow({{
        children: [
          makeCell("{i}.", 800),
          makeCell("{tahap}", 3500),
          makeCell("{tanggal}", 2500),
          makeCell("{mode}", 2560),
        ]
      }}),"""

    js = f"""
const {{
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, ShadingType, VerticalAlign
}} = require('docx');
const fs = require('fs');

const bdr = {{ style: BorderStyle.SINGLE, size: 1, color: "000000" }};
const borders = {{ top: bdr, bottom: bdr, left: bdr, right: bdr }};
const noBdr = {{ style: BorderStyle.NONE, size: 0, color: "FFFFFF" }};
const noBorders = {{ top: noBdr, bottom: noBdr, left: noBdr, right: noBdr }};

function makeCell(text, width, bold=false, align=AlignmentType.LEFT) {{
  return new TableCell({{
    borders, width: {{ size: width, type: WidthType.DXA }},
    margins: {{ top: 80, bottom: 80, left: 120, right: 120 }},
    children: [new Paragraph({{ alignment: align, children: [
      new TextRun({{ text: String(text), bold, font: "Times New Roman", size: 24 }})
    ]}})]
  }});
}}
function makeFree(text, width, bold=false, align=AlignmentType.LEFT) {{
  return new TableCell({{
    borders: noBorders, width: {{ size: width, type: WidthType.DXA }},
    margins: {{ top: 40, bottom: 40, left: 0, right: 0 }},
    children: [new Paragraph({{ alignment: align, children: [
      new TextRun({{ text: String(text), bold, font: "Times New Roman", size: 24 }})
    ]}})]
  }});
}}
function p(text, bold=false, align=AlignmentType.LEFT, size=24, indent=null) {{
  const o = {{ alignment: align, children: [
    new TextRun({{ text, bold, font: "Times New Roman", size }})
  ]}};
  if (indent) o.indent = indent;
  return new Paragraph(o);
}}
const gap = () => new Paragraph({{ children: [new TextRun({{ text:"", font:"Times New Roman", size:24 }})] }});
const RIGHT = AlignmentType.RIGHT;
const CENTER = AlignmentType.CENTER;
const LEFT = AlignmentType.LEFT;
const JUSTIFIED = AlignmentType.JUSTIFIED;

const doc = new Document({{
  sections: [{{
    properties: {{ page: {{
      size: {{ width: 11906, height: 16838 }},
      margin: {{ top: 1418, right: 1134, bottom: 1134, left: 1701 }}
    }}}},
    children: [
      p("{esc(institusi)}", true, CENTER, 28),
      gap(),

      new Table({{
        width: {{ size: 9071, type: WidthType.DXA }},
        columnWidths: [1800, 200, 4000, 3071],
        rows: [
          new TableRow({{ children: [
            makeFree("Nomor",1800), makeFree(":",200), makeFree("",4000),
            makeFree("{esc(tanggal_str)}",3071,false,RIGHT)
          ]}}),
          new TableRow({{ children: [
            makeFree("Lampiran",1800), makeFree(":",200), makeFree("1 (satu) berkas",4000), makeFree("",3071)
          ]}}),
          new TableRow({{ children: [
            makeFree("Hal",1800), makeFree(":",200),
            makeFree("Permohonan Izin Keikutsertaan {esc(lomba.get('nama_lomba',''))}",4000,true),
            makeFree("",3071)
          ]}}),
        ]
      }}),
      gap(),

      p("Yth.", false, LEFT, 24, {{ left:720 }}),
      p("Pimpinan / Penanggung Jawab", true, LEFT, 24, {{ left:720 }}),
      p("{esc(institusi)}", false, LEFT, 24, {{ left:720 }}),
      p("di Tempat", false, LEFT, 24, {{ left:720 }}),
      gap(),

      new Paragraph({{ alignment: JUSTIFIED, indent: {{ firstLine:720 }}, children: [
        new TextRun({{ font:"Times New Roman", size:24,
          text: "Sehubungan dengan akan diselenggarakannya {esc(lomba.get('nama_lomba',''))}. Dengan hormat, kami menyampaikan permohonan izin keikutsertaan lomba sebagaimana dimaksud. Pelaksanaan perlombaan tersebut terdapat pada Lampiran I surat ini. Adapun daftar peserta yang mengikuti kegiatan tersebut tercantum pada Lampiran II surat ini."
        }})
      ]}}),
      gap(),
      new Paragraph({{ alignment: JUSTIFIED, indent: {{ firstLine:720 }}, children: [
        new TextRun({{ font:"Times New Roman", size:24,
          text: "Demikian surat permohonan ini disampaikan, mohon perkenan persetujuan. Atas perhatiannya diucapkan terima kasih."
        }})
      ]}}),
      gap(), gap(),

      p("{esc(jabatan_ketua)}", false, LEFT, 24, {{ left:5500 }}),
      p("{esc(institusi)}", false, LEFT, 24, {{ left:5500 }}),
      gap(), gap(), gap(),
      p("{esc(ketua)}", true, LEFT, 24, {{ left:5500 }}),
      gap(), gap(),

      // ── LAMPIRAN I ──────────────────────────────────────────
      p("Lampiran I", true, RIGHT),
      p("Surat {esc(jabatan_ketua)}", false, RIGHT),
      p("{esc(institusi)}", false, RIGHT),
      p("Tanggal: {esc(tanggal_str)}", false, RIGHT),
      gap(),
      p("DETAIL LOMBA", true, CENTER, 26),
      gap(),
      new Table({{
        width: {{ size: 9071, type: WidthType.DXA }},
        columnWidths: [2500, 300, 6271],
        rows: [
          new TableRow({{ children: [ makeFree("Nama Lomba",2500), makeFree(":",300), makeFree("{esc(lomba.get('nama_lomba',''))}",6271) ]}}),
          new TableRow({{ children: [ makeFree("Penyelenggara",2500), makeFree(":",300), makeFree("{esc(lomba.get('penyelenggara',''))}",6271) ]}}),
          new TableRow({{ children: [ makeFree("Tempat",2500), makeFree(":",300), makeFree("{esc(lomba.get('tempat',''))}",6271) ]}}),
          new TableRow({{ children: [ makeFree("Biaya Pendaftaran",2500), makeFree(":",300), makeFree("{esc(lomba.get('biaya',''))}",6271) ]}}),
          new TableRow({{ children: [ makeFree("Hadiah Juara 1",2500), makeFree(":",300), makeFree("{esc(lomba.get('hadiah_1',''))}",6271) ]}}),
          new TableRow({{ children: [ makeFree("Hadiah Juara 2",2500), makeFree(":",300), makeFree("{esc(lomba.get('hadiah_2',''))}",6271) ]}}),
          new TableRow({{ children: [ makeFree("Hadiah Juara 3",2500), makeFree(":",300), makeFree("{esc(lomba.get('hadiah_3',''))}",6271) ]}}),
          new TableRow({{ children: [ makeFree("Link/Website",2500), makeFree(":",300), makeFree("{esc(lomba.get('link_lomba','') or '-')}",6271) ]}}),
        ]
      }}),
      gap(),
      p("TAHAPAN LOMBA", true, CENTER, 26),
      gap(),
      new Table({{
        width: {{ size: 9360, type: WidthType.DXA }},
        columnWidths: [800, 3500, 2500, 2560],
        rows: [
          new TableRow({{ tableHeader: true, children: [
            makeCell("No.",800,true,CENTER), makeCell("Tahap",3500,true,CENTER),
            makeCell("Tanggal",2500,true,CENTER), makeCell("Pelaksanaan",2560,true,CENTER),
          ]}}),
          {timeline_rows}
        ]
      }}),
      gap(), gap(),

      // ── LAMPIRAN II ─────────────────────────────────────────
      p("Lampiran II", true, RIGHT),
      p("Surat {esc(jabatan_ketua)}", false, RIGHT),
      p("{esc(institusi)}", false, RIGHT),
      p("Tanggal: {esc(tanggal_str)}", false, RIGHT),
      gap(),
      p("DAFTAR PESERTA {esc(lomba.get('nama_lomba','').upper())}", true, CENTER, 26),
      gap(),
      new Table({{
        width: {{ size: 9360, type: WidthType.DXA }},
        columnWidths: [800, 3560, 2000, 3000],
        rows: [
          new TableRow({{ tableHeader: true, children: [
            makeCell("No.",800,true,CENTER), makeCell("Nama",3560,true,CENTER),
            makeCell("Bidang/Kategori",2000,true,CENTER), makeCell("Keterangan",3000,true,CENTER),
          ]}}),
          ...Array.from({{length:5}}, (_,i) => new TableRow({{ children: [
            makeCell(String(i+1)+".",800), makeCell("",3560), makeCell("",2000), makeCell("",3000)
          ]}})),
        ]
      }}),
      gap(), gap(),

      // ── LAMPIRAN III ────────────────────────────────────────
      p("Lampiran III", true, RIGHT),
      p("Surat {esc(jabatan_ketua)}", false, RIGHT),
      p("{esc(institusi)}", false, RIGHT),
      p("Tanggal: {esc(tanggal_str)}", false, RIGHT),
      gap(),
      p("POSTER KEGIATAN LOMBA", true, CENTER, 26),
      gap(),
      p("[ Tempel poster lomba di sini ]", false, CENTER, 24),
      gap(),
      p("Sumber: {esc(lomba.get('link_lomba',''))}", false, LEFT, 22),
    ]
  }}]
}});

Packer.toBuffer(doc).then(buf => {{
  fs.writeFileSync("{output_path}", buf);
  console.log("OK");
}}).catch(e => {{ console.error(String(e)); process.exit(1); }});
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(js)
        js_path = f.name
    try:
        r = subprocess.run(["node", js_path], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[:500])
        return output_path
    finally:
        os.unlink(js_path)


# ─── TELEGRAM HANDLERS ────────────────────────────────────────────────────────
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Conversation states untuk input lomba manual
(
    L_NAMA, L_PENYELENGGARA, L_TEMPAT, L_BIAYA,
    L_HADIAH1, L_HADIAH2, L_HADIAH3, L_LINK,
    L_TIMELINE, L_CATATAN
) = range(20, 30)


async def cmd_tambah_lomba(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mulai input lomba step-by-step."""
    ctx.user_data["lomba"] = {}
    await update.message.reply_text(
        "🏆 *Tambah Lomba Baru*\n\n"
        "Langkah 1/9 — Ketik *nama lomba:*\n"
        "_(contoh: Hackathon Nasional 2026)_\n\n"
        "Ketik /batal untuk membatalkan.",
        parse_mode="Markdown"
    )
    return L_NAMA

async def l_nama(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["lomba"]["nama_lomba"] = update.message.text.strip()
    await update.message.reply_text(
        "🏛️ Langkah 2/9 — *Nama penyelenggara:*\n_(contoh: Universitas Indonesia)_",
        parse_mode="Markdown"
    )
    return L_PENYELENGGARA

async def l_penyelenggara(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["lomba"]["penyelenggara"] = update.message.text.strip()
    await update.message.reply_text(
        "📍 Langkah 3/9 — *Tempat pelaksanaan:*\n_(contoh: Daring / Luring - Jakarta / Daring dan Luring)_",
        parse_mode="Markdown"
    )
    return L_TEMPAT

async def l_tempat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["lomba"]["tempat"] = update.message.text.strip()
    await update.message.reply_text(
        "💰 Langkah 4/9 — *Biaya pendaftaran:*\n_(contoh: Gratis / Rp 150.000 / Rp 50.000 per orang)_",
        parse_mode="Markdown"
    )
    return L_BIAYA

async def l_biaya(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["lomba"]["biaya"] = update.message.text.strip()
    await update.message.reply_text(
        "🥇 Langkah 5/9 — *Hadiah Juara 1:*\n_(contoh: Rp 10.000.000 + Trophy / Tidak disebutkan)_",
        parse_mode="Markdown"
    )
    return L_HADIAH1

async def l_hadiah1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["lomba"]["hadiah_1"] = update.message.text.strip()
    await update.message.reply_text(
        "🥈 Langkah 6/9 — *Hadiah Juara 2:*",
        parse_mode="Markdown"
    )
    return L_HADIAH2

async def l_hadiah2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["lomba"]["hadiah_2"] = update.message.text.strip()
    await update.message.reply_text(
        "🥉 Langkah 7/9 — *Hadiah Juara 3:*",
        parse_mode="Markdown"
    )
    return L_HADIAH3

async def l_hadiah3(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["lomba"]["hadiah_3"] = update.message.text.strip()
    await update.message.reply_text(
        "🔗 Langkah 8/9 — *Link/website lomba:*\n_(ketik `-` jika tidak ada)_",
        parse_mode="Markdown"
    )
    return L_LINK

async def l_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["lomba"]["link_lomba"] = "" if val == "-" else val
    await update.message.reply_text(
        "📅 Langkah 9/9 — *Timeline / tahapan lomba:*\n\n"
        "Ketik setiap tahap dalam format:\n"
        "`Nama Tahap | Tanggal`\n\n"
        "Pisahkan tiap baris dengan Enter. Contoh:\n"
        "```\n"
        "Pembukaan Registrasi | 1 Mei 2026\n"
        "Penutupan Registrasi | 14 Juni 2026\n"
        "Technical Meeting | 19 Juni 2026\n"
        "Babak Penyisihan | 20 Juni 2026\n"
        "Final | 8 Juli 2026\n"
        "```\n"
        "_(Ketik `-` jika tidak ada timeline)_",
        parse_mode="Markdown"
    )
    return L_TIMELINE

async def l_timeline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    timeline = []
    if raw != "-":
        for line in raw.splitlines():
            line = line.strip()
            if "|" in line:
                parts = line.split("|", 1)
                timeline.append({"tahap": parts[0].strip(), "tanggal": parts[1].strip()})
            elif line:
                timeline.append({"tahap": line, "tanggal": ""})
    ctx.user_data["lomba"]["timeline"] = timeline
    await update.message.reply_text(
        "📝 *Catatan tambahan* (opsional):\n"
        "_(kategori, syarat peserta, info lain — atau ketik `-` untuk skip)_",
        parse_mode="Markdown"
    )
    return L_CATATAN

async def l_catatan(update: Update, ctx: ContextTypes.DEFAULT_TYPE, supabase):
    val = update.message.text.strip()
    ctx.user_data["lomba"]["catatan"] = "" if val == "-" else val

    chat_id = update.effective_chat.id
    saved = db_save_lomba(supabase, chat_id, ctx.user_data["lomba"])
    ctx.user_data.pop("lomba", None)

    resume = format_resume_lomba(saved)
    await update.message.reply_text(
        f"✅ *Lomba berhasil disimpan!*\n\n{resume}\n\n"
        f"💡 Gunakan `/proposal {saved.get('id','')}` untuk buat proposal Word.",
        parse_mode="Markdown"
    )
    return -1  # ConversationHandler.END


async def cmd_daftar_lomba(update: Update, ctx: ContextTypes.DEFAULT_TYPE, supabase):
    chat_id = update.effective_chat.id
    lomba_list = db_get_lomba(supabase, chat_id)

    if not lomba_list:
        await update.message.reply_text(
            "📭 Belum ada lomba tersimpan.\n\nGunakan /tambah\\_lomba untuk menambahkan.",
            parse_mode="Markdown"
        )
        return

    lines = [f"🏆 *Daftar Lomba Tersimpan ({len(lomba_list)})*\n{'─'*30}\n"]
    for i, l in enumerate(lomba_list, 1):
        lines.append(
            f"*{i}. {l.get('nama_lomba','?')}*\n"
            f"   📍 {l.get('tempat') or '-'}  💰 {l.get('biaya') or '-'}\n"
            f"   🆔 `{l.get('id','?')}`\n"
        )
    lines.append("💡 `/proposal <ID>` → buat proposal  |  `/detail_lomba <ID>` → detail lengkap")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_detail_lomba(update: Update, ctx: ContextTypes.DEFAULT_TYPE, supabase):
    if not ctx.args:
        await update.message.reply_text("Gunakan: `/detail_lomba <ID>`", parse_mode="Markdown")
        return
    lomba = db_get_lomba_by_id(supabase, ctx.args[0].strip())
    if not lomba:
        await update.message.reply_text("❌ Lomba tidak ditemukan.", parse_mode="Markdown")
        return
    await update.message.reply_text(format_resume_lomba(lomba), parse_mode="Markdown")


async def cmd_hapus_lomba(update: Update, ctx: ContextTypes.DEFAULT_TYPE, supabase):
    if not ctx.args:
        await update.message.reply_text("Gunakan: `/hapus_lomba <ID>`", parse_mode="Markdown")
        return
    if db_delete_lomba(supabase, ctx.args[0].strip()):
        await update.message.reply_text("🗑️ Data lomba berhasil dihapus.")
    else:
        await update.message.reply_text("❌ Lomba tidak ditemukan.", parse_mode="Markdown")


async def cmd_proposal(update: Update, ctx: ContextTypes.DEFAULT_TYPE, supabase):
    if not ctx.args:
        await update.message.reply_text(
            "Gunakan: `/proposal <ID>`\n_ID ada di /daftar\\_lomba_",
            parse_mode="Markdown"
        )
        return

    lomba = db_get_lomba_by_id(supabase, ctx.args[0].strip())
    if not lomba:
        await update.message.reply_text("❌ Lomba tidak ditemukan.", parse_mode="Markdown")
        return

    chat_id = update.effective_chat.id
    institusi = ctx.bot_data.get(f"institusi_{chat_id}", "Nama Institusi")
    ketua     = ctx.bot_data.get(f"ketua_{chat_id}",     "Nama Ketua")
    jabatan   = ctx.bot_data.get(f"jabatan_{chat_id}",   "Ketua Organisasi")

    msg = await update.message.reply_text("📄 Membuat proposal Word... mohon tunggu.")
    try:
        nama_file = re.sub(r'[^\w\s-]', '', lomba.get("nama_lomba","lomba"))
        nama_file = nama_file.strip().replace(" ","_")[:40]
        output_path = f"/tmp/Proposal_{nama_file}.docx"

        generate_proposal_docx(lomba, output_path, institusi, ketua, jabatan)

        with open(output_path, "rb") as f:
            await ctx.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=f"Proposal_{nama_file}.docx",
                caption=(
                    f"📄 *Proposal — {lomba.get('nama_lomba','')}*\n\n"
                    "✅ *Tinggal dilengkapi:*\n"
                    "  • Nomor surat\n"
                    "  • Lampiran II: daftar nama peserta\n"
                    "  • Lampiran III: tempel poster\n\n"
                    f"⚙️ Ganti nama institusi: `/set_institusi Nama Institusimu`"
                ),
                parse_mode="Markdown"
            )
        await msg.delete()
        os.unlink(output_path)
    except Exception as e:
        logger.error(f"Error generate proposal: {e}")
        await msg.edit_text(f"❌ Gagal buat proposal: {str(e)[:300]}")


async def cmd_set_institusi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            f"⚙️ *Pengaturan Proposal*\n\n"
            f"🏛️ Institusi: `{ctx.bot_data.get(f'institusi_{chat_id}','(belum diset)')}`\n"
            f"👤 Ketua: `{ctx.bot_data.get(f'ketua_{chat_id}','(belum diset)')}`\n"
            f"💼 Jabatan: `{ctx.bot_data.get(f'jabatan_{chat_id}','(belum diset)')}`\n\n"
            "*Cara ubah:*\n"
            "`/set_institusi Nama Institusi`\n"
            "`/set_ketua Nama Lengkap Ketua`\n"
            "`/set_jabatan Jabatan Ketua`",
            parse_mode="Markdown"
        )
        return
    ctx.bot_data[f"institusi_{update.effective_chat.id}"] = " ".join(ctx.args)
    await update.message.reply_text(f"✅ Institusi: *{' '.join(ctx.args)}*", parse_mode="Markdown")

async def cmd_set_ketua(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Gunakan: `/set_ketua Nama Lengkap`", parse_mode="Markdown"); return
    ctx.bot_data[f"ketua_{update.effective_chat.id}"] = " ".join(ctx.args)
    await update.message.reply_text(f"✅ Ketua: *{' '.join(ctx.args)}*", parse_mode="Markdown")

async def cmd_set_jabatan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Gunakan: `/set_jabatan Jabatan`", parse_mode="Markdown"); return
    ctx.bot_data[f"jabatan_{update.effective_chat.id}"] = " ".join(ctx.args)
    await update.message.reply_text(f"✅ Jabatan: *{' '.join(ctx.args)}*", parse_mode="Markdown")
