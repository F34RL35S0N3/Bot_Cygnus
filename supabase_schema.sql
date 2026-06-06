-- ============================================================
-- DeadlineBot — Supabase Schema
-- Jalankan query ini di Supabase SQL Editor
-- ============================================================

-- Tabel utama untuk menyimpan semua tugas
CREATE TABLE IF NOT EXISTS tasks (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    chat_id     TEXT        NOT NULL,          -- ID grup/chat Telegram
    title       TEXT        NOT NULL,          -- Judul tugas
    deadline    DATE        NOT NULL,          -- Tanggal deadline
    assignee    TEXT,                          -- Nama yang bertanggung jawab
    priority    TEXT DEFAULT 'medium'          -- 'high' | 'medium' | 'low'
                CHECK (priority IN ('high', 'medium', 'low')),
    status      TEXT DEFAULT 'pending'         -- 'pending' | 'done'
                CHECK (status IN ('pending', 'done')),
    added_by    TEXT,                          -- Siapa yang menambahkan
    created_at  TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ                   -- Kapan diselesaikan (nullable)
);

-- Index untuk query cepat berdasarkan chat dan status
CREATE INDEX IF NOT EXISTS idx_tasks_chat_status
    ON tasks (chat_id, status);

-- Index untuk query berdasarkan deadline
CREATE INDEX IF NOT EXISTS idx_tasks_deadline
    ON tasks (deadline);

-- ── Row Level Security (opsional, untuk keamanan ekstra) ───
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;

-- Policy: izinkan semua operasi via service key (backend bot)
CREATE POLICY "Allow all via service role"
    ON tasks
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- ── Contoh data untuk testing ─────────────────────────────
/*
INSERT INTO tasks (chat_id, title, deadline, assignee, priority, added_by) VALUES
('-100123456789', 'Laporan Bulanan Q4',     CURRENT_DATE + 3,  'Budi',   'high',   'Admin'),
('-100123456789', 'Review Design Mockup',   CURRENT_DATE + 1,  'Ani',    'medium', 'Admin'),
('-100123456789', 'Deploy Update v2.1',     CURRENT_DATE + 7,  'Deni',   'high',   'Admin'),
('-100123456789', 'Meeting Summary Notes',  CURRENT_DATE,      'Semua',  'low',    'Admin');
*/
