-- Arsip email masuk untuk seluruh alamat @bangkah.my.id.
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  mailbox TEXT NOT NULL,
  to_addr TEXT NOT NULL,
  from_addr TEXT NOT NULL,
  subject TEXT NOT NULL,
  text_body TEXT NOT NULL DEFAULT '',
  html_body TEXT NOT NULL DEFAULT '',
  attachments_json TEXT NOT NULL DEFAULT '[]',
  raw_key TEXT NOT NULL DEFAULT '',
  size INTEGER NOT NULL DEFAULT 0,
  received_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_mailbox ON messages(mailbox, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_received ON messages(received_at DESC);
