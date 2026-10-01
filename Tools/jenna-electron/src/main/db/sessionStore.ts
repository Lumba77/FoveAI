/**
 * sessionStore.ts — SQLite session + message persistence
 *
 * Replaces sessions.json from jenna-vscode with a proper SQLite database.
 * Schema: sessions + messages with FK relationship.
 */

import Database from 'better-sqlite3';
import * as crypto from 'crypto';

export interface Session {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count?: number;
}

export interface Message {
  id: string;
  session_id: string;
  role: string;
  content: string;
  ts: number;
}

export class SessionStore {
  private db: Database.Database;

  constructor(dbPath: string) {
    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
    this.db.pragma('foreign_keys = ON');
    this._init();
  }

  private _init(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS sessions (
        id         TEXT PRIMARY KEY,
        title      TEXT NOT NULL DEFAULT 'New Session',
        created_at INTEGER NOT NULL DEFAULT (unixepoch('now', 'subsec') * 1000),
        updated_at INTEGER NOT NULL DEFAULT (unixepoch('now', 'subsec') * 1000)
      );

      CREATE TABLE IF NOT EXISTS messages (
        id         TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        role       TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
        content    TEXT NOT NULL,
        ts         INTEGER NOT NULL DEFAULT (unixepoch('now', 'subsec') * 1000)
      );

      CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, ts);
      CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
    `);
  }

  // ── Sessions ───────────────────────────────────────────────────────────────

  createSession(title: string = 'New Session'): Session {
    const id = crypto.randomUUID();
    const now = Date.now();
    this.db.prepare(
      'INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)'
    ).run(id, title, now, now);
    return { id, title, created_at: now, updated_at: now };
  }

  listSessions(): Session[] {
    return this.db.prepare<[], Session & { message_count: number }>(`
      SELECT s.*, COUNT(m.id) as message_count
      FROM sessions s
      LEFT JOIN messages m ON m.session_id = s.id
      GROUP BY s.id
      ORDER BY s.updated_at DESC
      LIMIT 100
    `).all() as (Session & { message_count: number })[];
  }

  getSession(id: string): Session | null {
    return (this.db.prepare<[string], Session>(
      'SELECT * FROM sessions WHERE id = ?'
    ).get(id) as Session | undefined) ?? null;
  }

  renameSession(id: string, title: string): void {
    this.db.prepare(
      'UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?'
    ).run(title.slice(0, 200), Date.now(), id);
  }

  deleteSession(id: string): void {
    this.db.prepare('DELETE FROM sessions WHERE id = ?').run(id);
  }

  touchSession(id: string): void {
    this.db.prepare(
      'UPDATE sessions SET updated_at = ? WHERE id = ?'
    ).run(Date.now(), id);
  }

  // ── Messages ───────────────────────────────────────────────────────────────

  addMessage(sessionId: string, role: string, content: string): string {
    const id = crypto.randomUUID();
    const now = Date.now();
    this.db.prepare(
      'INSERT INTO messages (id, session_id, role, content, ts) VALUES (?, ?, ?, ?, ?)'
    ).run(id, sessionId, role, content, now);
    // Update session timestamp
    this.touchSession(sessionId);
    return id;
  }

  getMessages(sessionId: string, limit = 200): Message[] {
    return this.db.prepare<[string, number], Message>(
      'SELECT * FROM messages WHERE session_id = ? ORDER BY ts ASC LIMIT ?'
    ).all(sessionId, limit) as Message[];
  }

  deleteMessage(id: string): void {
    this.db.prepare('DELETE FROM messages WHERE id = ?').run(id);
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  close(): void {
    try { this.db.close(); } catch { /* ignore */ }
  }
}
