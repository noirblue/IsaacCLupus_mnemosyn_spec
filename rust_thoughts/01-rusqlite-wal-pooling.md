# 01: rusqlite with WAL Mode and Connection Pooling

## Question
Does a production-ready Rust SQLite stack exist that can replace Python's sqlite3 for Mnemosyne's core engine?

## Answer
Yes. The ecosystem is mature and battle-tested.

## Key Crates

| Crate | Version | Purpose |
|---|---|---|
| `rusqlite` | 0.34+ | Core SQLite bindings |
| `r2d2_sqlite` | 0.25+ | Connection pooling |
| `tokio-rusqlite` | 0.6+ | Async wrapper via `spawn_blocking` |

## WAL Mode Setup

```rust
use rusqlite::Connection;

let conn = Connection::open("state.db")?;
conn.execute_batch("
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;
    PRAGMA foreign_keys=ON;
")?;
```

## Connection Pooling 

```rust
use r2d2::Pool;
use r2d2_sqlite::SqliteConnectionManager;

let manager = SqliteConnectionManager::file("state.db");
let pool = Pool::builder()
    .max_size(10)
    .connection_customizer(Box::new(|conn| {
        conn.execute_batch("PRAGMA journal_mode=WAL;")?;
        Ok(())
    }))
    .build(manager)?;
```
    
## Async Pattern

```rust
use tokio_rusqlite::Connection;

let conn = Connection::open("state.db").await?;
conn.call(|conn| {
    conn.execute("INSERT INTO pages ...", [])?;
    Ok(())
}).await?;
```

## Limitations

| Feature          | Status                   | Workaround                        |
| ---------------- | ------------------------ | --------------------------------- |
| Migration system | Not built-in             | Use `refinery` or `sqlx migrate`  |
| ORM              | No SQLAlchemy equivalent | Use `diesel` or raw SQL + `serde` |
| Read replicas    | Not native               | WAL allows concurrent readers     |

## Production Precedents

- `atuin` — shell history sync
- `sccache` — compiler cache
- `ruff` — Python linter (SQLite cache)

## Conclusion

`rusqlite` + `r2d2` + `tokio-rusqlite` is production-ready for Mnemosyne's core engine. No blockers.
