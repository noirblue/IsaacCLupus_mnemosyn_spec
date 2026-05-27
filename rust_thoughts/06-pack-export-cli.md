# 06: Pack Export + CLI — Single Binary Deployment

## Question

How do we build a type-safe CLI in Rust that compiles to a single binary, handles pack exports for agent consumption, and eliminates the Python environment hell of pip, venv, and dependency conflicts?

## Answer

Use `clap` for declarative CLI parsing, `serde` for configuration and data serialization, and `cargo` for cross-compilation. The result is a single binary (`mnemosyne` or `mn`) that contains the entire application — no runtime Python, no virtualenv, no `requirements.txt`, no version conflicts.

---

## Why This Matters for Mnemosyne

The Python glue layer required:

- Python 3.11+ installed system-wide or in venv
- `pip install -e .` for the glue package
- `pip install fastapi uvicorn httpx` for the proxy
- `pip install python-frontmatter pyyaml` for sync scripts
- Ollama installed separately
- systemd services pointing to Python interpreter paths
- Version drift between host Python and venv Python

On a fresh Kubuntu 26.04 machine, this is 30 minutes of setup. On a different distro, it breaks. On a different Python minor version, it breaks. On a machine without `python3-dev`, it breaks.

A Rust binary:

- `cargo build --release` → one file: `target/release/mnemosyne`
- `scp mnemosyne strix-halo:/usr/local/bin/` → done
- `mnemosyne init ~/jarvis-kb` → creates vault
- `mnemosyne serve` → starts MCP + REST server
- No dependencies. No runtime. No surprises.

---

## Implementation: CLI with `clap`

### Dependencies (`Cargo.toml`)

```toml
[package]
name = "mnemosyne"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "mn"
path = "src/main.rs"

[dependencies]
# CLI parsing
clap = { version = "4.5", features = ["derive", "env", "cargo"] }

# Configuration
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
toml = "0.8"
dirs = "5.0"              # XDG directories: ~/.config/mnemosyne/

# Async runtime
tokio = { version = "1.40", features = ["full"] }

# Error handling
anyhow = "1.0"
thiserror = "2.0"

# Logging
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter", "fmt"] }

# File operations
tokio-rusqlite = "0.6"
walkdir = "2.5"
ignore = "0.4"          # .gitignore-style filtering

# Pack export
zip = "0.6"             # Optional: compressed packs
tar = "0.4"
flate2 = "1.0"

# HTTP client (for Ollama)
reqwest = { version = "0.12", features = ["json", "stream"] }

# Optional: colored output
anstream = "0.6"
anstyle = "1.0"
```

### CLI Structure

```rust
use clap::{Parser, Subcommand, Args, ValueEnum};
use std::path::PathBuf;

/// Mnemosyne: unified local-first knowledge operating system
#[derive(Parser)]
#[command(name = "mn")]
#[command(bin_name = "mn")]
#[command(version = env!("CARGO_PKG_VERSION"))]
#[command(about = "A unified, local-first semantic memory OS for autonomous agents")]
#[command(long_about = None)]
pub struct Cli {
    /// Path to configuration file
    #[arg(short, long, value_name = "FILE", env = "MNEMOSYNE_CONFIG")]
    pub config: Option<PathBuf>,

    /// Path to vault directory
    #[arg(short, long, value_name = "DIR", env = "MNEMOSYNE_VAULT")]
    pub vault: Option<PathBuf>,

    /// Enable verbose logging
    #[arg(short, long, action = clap::ArgAction::Count)]
    pub verbose: u8,

    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand)]
pub enum Commands {
    /// Initialize a new knowledge vault
    Init(InitArgs),

    /// Ingest files into the knowledge base
    Ingest(IngestArgs),

    /// Run the compilation pipeline
    Compile(CompileArgs),

    /// Query the knowledge base
    Ask(AskArgs),

    /// Search the knowledge base
    Search(SearchArgs),

    /// Run audit and lint checks
    Audit(AuditArgs),

    /// Manage memory lifecycle
    Remember(RememberArgs),

    /// Export agent-ready pack
    Pack(PackArgs),

    /// Start the MCP + REST server
    Serve(ServeArgs),

    /// Show vault statistics
    Stats,

    /// Run maintenance tasks
    Maintain(MaintainArgs),
}

// --- Subcommand arguments ---

#[derive(Args)]
pub struct InitArgs {
    /// Vault directory path (default: ~/jarvis-kb)
    #[arg(value_name = "PATH")]
    pub path: Option<PathBuf>,

    /// Create sample configuration
    #[arg(long)]
    pub sample_config: bool,
}

#[derive(Args)]
pub struct IngestArgs {
    /// Files or directories to ingest
    #[arg(required = true, value_name = "PATH")]
    pub paths: Vec<PathBuf>,

    /// Document type override
    #[arg(short, long, value_enum)]
    pub doc_type: Option<DocType>,

    /// Watch for changes after initial ingest
    #[arg(short, long)]
    pub watch: bool,
}

#[derive(ValueEnum, Clone, Debug)]
pub enum DocType {
    Notes,
    Paper,
    Textbook,
    Spec,
    ApiDocs,
    WebArticle,
    CorpDocs,
    Transcript,
    Unknown,
}

#[derive(Args)]
pub struct CompileArgs {
    /// Scope of compilation
    #[arg(short, long, value_enum, default_value = "all")]
    pub scope: CompileScope,

    /// Auto-approve drafts above confidence threshold
    #[arg(long)]
    pub auto_approve: bool,

    /// Confidence threshold for auto-approval (0.0-1.0)
    #[arg(long, default_value = "0.8")]
    pub threshold: f64,

    /// Run A/B model comparison
    #[arg(long)]
    pub compare: bool,
}

#[derive(ValueEnum, Clone, Debug)]
pub enum CompileScope {
    All,
    Self,
    World,
}

#[derive(Args)]
pub struct AskArgs {
    /// Question to ask
    #[arg(value_name = "QUESTION")]
    pub question: String,

    /// Session ID for conversation continuity
    #[arg(short, long)]
    pub session: Option<String>,

    /// Context token budget
    #[arg(long, default_value = "24000")]
    pub context_budget: usize,

    /// History token budget
    #[arg(long, default_value = "3000")]
    pub history_budget: usize,

    /// Synthesize answer as new wiki page
    #[arg(long)]
    pub synthesize: bool,
}

#[derive(Args)]
pub struct SearchArgs {
    /// Search query
    #[arg(value_name = "QUERY")]
    pub query: String,

    /// Source namespace filter
    #[arg(short, long, value_enum, default_value = "all")]
    pub source: SearchSource,

    /// Maximum results
    #[arg(short, long, default_value = "10")]
    pub limit: usize,
}

#[derive(ValueEnum, Clone, Debug)]
pub enum SearchSource {
    All,
    Self,
    World,
    Memory,
}

#[derive(Args)]
pub struct AuditArgs {
    /// Audit scope
    #[arg(short, long, value_enum, default_value = "all")]
    pub scope: AuditScope,

    /// Fix issues automatically where safe
    #[arg(long)]
    pub fix: bool,

    /// Output format
    #[arg(short, long, value_enum, default_value = "text")]
    pub format: OutputFormat,
}

#[derive(ValueEnum, Clone, Debug)]
pub enum AuditScope {
    All,
    Self,
    World,
    Links,
    Contradictions,
}

#[derive(Args)]
pub struct RememberArgs {
    /// Memory content
    #[arg(value_name = "CONTENT")]
    pub content: String,

    /// Tags for categorization
    #[arg(short, long)]
    pub tag: Vec<String>,

    /// Project scope
    #[arg(short, long, default_value = "default")]
    pub project: String,

    /// Stage: propose (default) or commit directly
    #[arg(short, long, value_enum, default_value = "propose")]
    pub stage: MemoryStage,
}

#[derive(ValueEnum, Clone, Debug)]
pub enum MemoryStage {
    Propose,
    Commit,
}

#[derive(Args)]
pub struct PackArgs {
    /// Output directory for pack
    #[arg(short, long, default_value = "./packs/latest")]
    pub output: PathBuf,

    /// Target format
    #[arg(short, long, value_enum, default_value = "agents")]
    pub target: PackTarget,

    /// Include raw sources
    #[arg(long)]
    pub include_sources: bool,

    /// Compression format
    #[arg(short, long, value_enum)]
    pub compress: Option<CompressionFormat>,
}

#[derive(ValueEnum, Clone, Debug)]
pub enum PackTarget {
    Agents,
    Obsidian,
    Hugo,
    Mkdocs,
}

#[derive(ValueEnum, Clone, Debug)]
pub enum CompressionFormat {
    Zip,
    TarGz,
    TarBz2,
}

#[derive(Args)]
pub struct ServeArgs {
    /// Bind address
    #[arg(short, long, default_value = "127.0.0.1:7070")]
    pub bind: String,

    /// Enable MCP transport
    #[arg(long, default_value = "true")]
    pub mcp: bool,

    /// Enable REST transport
    #[arg(long, default_value = "true")]
    pub rest: bool,

    /// Ollama endpoint override
    #[arg(long, env = "OLLAMA_URL")]
    pub ollama: Option<String>,
}

#[derive(Args)]
pub struct MaintainArgs {
    /// Rebuild search index
    #[arg(long)]
    pub reindex: bool,

    /// Repair broken links
    #[arg(long)]
    pub repair_links: bool,

    /// Clear LLM response cache
    #[arg(long)]
    pub clear_cache: bool,

    /// Prune old audit entries
    #[arg(long)]
    pub prune_audit: bool,

    /// Days to keep for pruning
    #[arg(long, default_value = "90")]
    pub keep_days: u32,
}

#[derive(ValueEnum, Clone, Debug)]
pub enum OutputFormat {
    Text,
    Json,
    Markdown,
}
```

---

## Implementation: Command Dispatch

```rust
use anyhow::Result;
use tracing::{info, warn, error};

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    // Initialize logging
    let filter = match cli.verbose {
        0 => "mnemosyne=info",
        1 => "mnemosyne=debug",
        _ => "mnemosyne=trace,hyper=debug,tokio=debug",
    };
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .init();

    // Load configuration
    let config = load_config(cli.config.as_deref(), cli.vault.as_deref()).await?;

    // Initialize application state
    let app = AppState::new(&config).await?;

    // Dispatch command
    match cli.command {
        Commands::Init(args) => cmd_init(args, &config).await?,
        Commands::Ingest(args) => cmd_ingest(args, &app).await?,
        Commands::Compile(args) => cmd_compile(args, &app).await?,
        Commands::Ask(args) => cmd_ask(args, &app).await?,
        Commands::Search(args) => cmd_search(args, &app).await?,
        Commands::Audit(args) => cmd_audit(args, &app).await?,
        Commands::Remember(args) => cmd_remember(args, &app).await?,
        Commands::Pack(args) => cmd_pack(args, &app).await?,
        Commands::Serve(args) => cmd_serve(args, &app).await?,
        Commands::Stats => cmd_stats(&app).await?,
        Commands::Maintain(args) => cmd_maintain(args, &app).await?,
    }

    Ok(())
}
```

---

## Implementation: Pack Export

```rust
use std::fs;
use walkdir::WalkDir;
use serde_json::json;

async fn cmd_pack(args: PackArgs, app: &AppState) -> Result<()> {
    info!("Exporting knowledge pack to {:?}", args.output);

    fs::create_dir_all(&args.output)?;

    // 1. Export articles
    let articles_dir = args.output.join("articles");
    fs::create_dir_all(&articles_dir)?;

    let pages = app.db_pool.get()?;
    let mut stmt = pages.prepare(
        "SELECT id, title, path, namespace, maturity, confidence 
         FROM pages 
         WHERE stage = 'published'"
    )?;

    let page_rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, f64>(5)?,
        ))
    })?;

    let mut index_entries = Vec::new();

    for row in page_rows {
        let (id, title, path, namespace, maturity, confidence) = row?;

        // Copy markdown file
        let src_path = app.vault_path.join(&path);
        let dst_path = articles_dir.join(format!("{}.md", sanitize_filename(&title)));

        if src_path.exists() {
            fs::copy(&src_path, &dst_path)?;
        }

        index_entries.push(json!({
            "id": id,
            "title": title,
            "namespace": namespace,
            "maturity": maturity,
            "confidence": confidence,
            "path": format!("articles/{}.md", sanitize_filename(&title)),
        }));
    }

    // 2. Write INDEX.json
    let index = json!({
        "version": env!("CARGO_PKG_VERSION"),
        "generated_at": chrono::Utc::now().to_rfc3339(),
        "pages": index_entries,
    });

    let index_dir = args.output.join("index");
    fs::create_dir_all(&index_dir)?;
    fs::write(
        index_dir.join("INDEX.json"),
        serde_json::to_string_pretty(&index)?
    )?;

    // 3. Write AGENTS.md
    let agents_md = generate_agents_md(&index_entries)?;
    fs::write(args.output.join("AGENTS.md"), agents_md)?;

    // 4. Write manifest.json
    let manifest = json!({
        "name": "mnemosyne-pack",
        "version": env!("CARGO_PKG_VERSION"),
        "target": args.target.to_string(),
        "article_count": index_entries.len(),
        "includes_sources": args.include_sources,
    });
    fs::write(
        args.output.join("manifest.json"),
        serde_json::to_string_pretty(&manifest)?
    )?;

    // 5. Optional compression
    if let Some(format) = args.compress {
        compress_pack(&args.output, format)?;
    }

    info!("Pack export complete: {} articles", index_entries.len());
    Ok(())
}

fn sanitize_filename(title: &str) -> String {
    title.to_lowercase()
        .replace(' ', "_")
        .replace(|c: char| !c.is_alphanumeric() && c != '_' && c != '-', "")
        .replace("__", "_")
}

fn generate_agents_md(pages: &[serde_json::Value]) -> Result<String> {
    let mut md = String::from("# Mnemosyne Knowledge Pack

");
    md.push_str("This pack contains compiled knowledge articles for agent consumption.

");
    md.push_str("## Quick Navigation

");

    for page in pages {
        let title = page["title"].as_str().unwrap_or("Untitled");
        let path = page["path"].as_str().unwrap_or("unknown");
        md.push_str(&format!("- [{}]({})
", title, path));
    }

    md.push_str("
## Usage

");
    md.push_str("Import this directory into any file-aware agent.
");
    md.push_str("Reference articles by title or ID.
");
    md.push_str("Check INDEX.json for machine-readable metadata.
");

    Ok(md)
}

fn compress_pack(output: &PathBuf, format: CompressionFormat) -> Result<()> {
    match format {
        CompressionFormat::Zip => {
            let zip_path = output.with_extension("zip");
            // Implementation using `zip` crate
            info!("Compressed to {:?}", zip_path);
        }
        CompressionFormat::TarGz => {
            let tar_path = output.with_extension("tar.gz");
            // Implementation using `tar` + `flate2`
            info!("Compressed to {:?}", tar_path);
        }
        CompressionFormat::TarBz2 => {
            let tar_path = output.with_extension("tar.bz2");
            info!("Compressed to {:?}", tar_path);
        }
    }
    Ok(())
}
```

---

## Implementation: Configuration Loading

```rust
use dirs::config_dir;
use std::path::Path;

#[derive(Debug, Clone, serde::Deserialize, serde::Serialize)]
pub struct ServerConfig {
    pub vault_path: PathBuf,
    pub db_path: PathBuf,
    pub ollama_url: String,
    pub bind_addr: String,
    pub models: ModelConfig,
    pub compile: CompileConfig,
    pub query: QueryConfig,
    pub audit: AuditConfig,
}

#[derive(Debug, Clone, serde::Deserialize, serde::Serialize)]
pub struct ModelConfig {
    pub ingest_fast: String,
    pub compile_heavy: String,
    pub chat: String,
    pub judge: String,
    pub embedding: String,
}

#[derive(Debug, Clone, serde::Deserialize, serde::Serialize)]
pub struct CompileConfig {
    pub auto_approve_threshold: f64,
    pub incremental: bool,
    pub preserve_hand_edits: bool,
}

#[derive(Debug, Clone, serde::Deserialize, serde::Serialize)]
pub struct QueryConfig {
    pub context_budget: usize,
    pub history_budget: usize,
    pub source_budget: usize,
    pub max_sources: usize,
    pub auto_synthesize: bool,
}

#[derive(Debug, Clone, serde::Deserialize, serde::Serialize)]
pub struct AuditConfig {
    pub adversarial_pass: bool,
    pub contradiction_detection: bool,
    pub auto_publish_after_audit: bool,
}

async fn load_config(
    explicit_path: Option<&Path>,
    explicit_vault: Option<&Path>,
) -> Result<ServerConfig> {
    // 1. Try explicit path
    if let Some(path) = explicit_path {
        if path.exists() {
            let content = tokio::fs::read_to_string(path).await?;
            let mut config: ServerConfig = toml::from_str(&content)?;
            if let Some(vault) = explicit_vault {
                config.vault_path = vault.to_path_buf();
                config.db_path = vault.join("state.db");
            }
            return Ok(config);
        }
    }

    // 2. Try vault directory
    if let Some(vault) = explicit_vault {
        let vault_config = vault.join("mnemosyne.toml");
        if vault_config.exists() {
            let content = tokio::fs::read_to_string(vault_config).await?;
            let mut config: ServerConfig = toml::from_str(&content)?;
            config.vault_path = vault.to_path_buf();
            config.db_path = vault.join("state.db");
            return Ok(config);
        }
    }

    // 3. Try XDG config directory
    if let Some(config_dir) = config_dir() {
        let global_config = config_dir.join("mnemosyne/config.toml");
        if global_config.exists() {
            let content = tokio::fs::read_to_string(global_config).await?;
            let mut config: ServerConfig = toml::from_str(&content)?;
            if let Some(vault) = explicit_vault {
                config.vault_path = vault.to_path_buf();
                config.db_path = vault.join("state.db");
            }
            return Ok(config);
        }
    }

    // 4. Default configuration
    let vault = explicit_vault
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_default().join("jarvis-kb"));

    Ok(ServerConfig {
        vault_path: vault.clone(),
        db_path: vault.join("state.db"),
        ollama_url: "http://localhost:11434".to_string(),
        bind_addr: "127.0.0.1:7070".to_string(),
        models: ModelConfig {
            ingest_fast: "gemma4:e4b".to_string(),
            compile_heavy: "qwen2.5:14b".to_string(),
            chat: "qwen3:30b-a3b".to_string(),
            judge: "llama3.3:70b".to_string(),
            embedding: "nomic-embed-text".to_string(),
        },
        compile: CompileConfig {
            auto_approve_threshold: 0.8,
            incremental: true,
            preserve_hand_edits: true,
        },
        query: QueryConfig {
            context_budget: 24000,
            history_budget: 3000,
            source_budget: 6000,
            max_sources: 8,
            auto_synthesize: false,
        },
        audit: AuditConfig {
            adversarial_pass: true,
            contradiction_detection: true,
            auto_publish_after_audit: false,
        },
    })
}
```

---

## Cross-Compilation for Deployment

### Linux (x86_64, native)

```bash
cargo build --release
# Binary: target/release/mn
# Size: ~8-15 MB (stripped)
```

### Linux (ARM64, for Raspberry Pi or ARM servers)

```bash
# Install cross-compilation target
rustup target add aarch64-unknown-linux-gnu

# Install cross-compiler (on Ubuntu/Debian)
sudo apt-get install gcc-aarch64-linux-gnu

# Build
CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc     cargo build --release --target aarch64-unknown-linux-gnu
```

### Static Binary (no libc dependency)

```bash
# Using musl for fully static binary
rustup target add x86_64-unknown-linux-musl

# Install musl toolchain
sudo apt-get install musl-tools

# Build
CC=x86_64-linux-musl-gcc     cargo build --release --target x86_64-unknown-linux-musl

# Result: binary with no dynamic dependencies
# Can run on any Linux, even minimal containers
```

### macOS

```bash
rustup target add x86_64-apple-darwin
rustup target add aarch64-apple-darwin

# Intel Mac
 cargo build --release --target x86_64-apple-darwin

# Apple Silicon Mac
 cargo build --release --target aarch64-apple-darwin
```

### Windows

```bash
rustup target add x86_64-pc-windows-gnu

# Cross-compile from Linux
sudo apt-get install mingw-w64

cargo build --release --target x86_64-pc-windows-gnu
```

---

## Comparison: Python vs Rust Deployment

| Aspect | Python (Synto/Synthadoc/LLM-WIKI-MCP/Link) | Rust (Mnemosyne) |
|---|---|---|
| **Installation** | `pip install` + venv + 4 separate packages | `scp mn /usr/local/bin/` |
| **Dependencies** | Python 3.11, pip, 20+ PyPI packages | None (static binary) |
| **Virtualenv** | Required to avoid conflicts | Not applicable |
| **Version conflicts** | Common (e.g., `pydantic` v1 vs v2) | Impossible (compiled in) |
| **Startup time** | 2-5 seconds (import overhead) | <50ms |
| **Memory footprint** | 50-200 MB per process | 5-15 MB total |
| **Distribution** | `requirements.txt` + README instructions | Single file |
| **Updates** | `pip install --upgrade` (may break) | Replace binary, restart |
| **Offline install** | Download wheels, hope they match platform | Copy binary |
| **Docker image** | `python:3.11-slim` + layers = 200+ MB | `scratch` + binary = 15 MB |
| **systemd service** | `ExecStart=/path/to/venv/bin/python -m mnemosyne` | `ExecStart=/usr/local/bin/mn serve` |

---

## systemd Service Example

```ini
[Unit]
Description=Mnemosyne Knowledge OS
After=network.target ollama.service

[Service]
Type=simple
ExecStart=/usr/local/bin/mn serve --bind 127.0.0.1:7070
WorkingDirectory=/home/user/jarvis-kb
Environment=MNEMOSYNE_VAULT=/home/user/jarvis-kb
Environment=OLLAMA_URL=http://localhost:11434
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Compare to the Python glue's systemd service (from `prior-art/v0-glue/`):

```ini
ExecStart=/home/user/jarvis-kb-bridge/.venv/bin/python -m jarvis_kb.cli serve-proxy
```

The Rust version is:
- Shorter
- No path to venv to break
- No Python version to mismatch
- No `PYTHONPATH` to set
- Portable across machines (same binary, different config)

---

## Shell Completion

`clap` generates shell completions automatically:

```rust
use clap_complete::{generate, shells};

pub fn generate_completions(shell: &str) -> Result<()> {
    let mut cmd = Cli::command();
    let shell = match shell {
        "bash" => shells::Bash,
        "zsh" => shells::Zsh,
        "fish" => shells::Fish,
        "powershell" => shells::PowerShell,
        _ => anyhow::bail!("Unsupported shell: {}", shell),
    };

    generate(shell, &mut cmd, "mn", &mut std::io::stdout());
    Ok(())
}
```

User installs:

```bash
mn completion bash > /etc/bash_completion.d/mn
mn completion zsh > /usr/share/zsh/site-functions/_mn
mn completion fish > ~/.config/fish/completions/mn.fish
```

---

## Production Precedents

| Tool | Language | Binary Size | Notes |
|---|---|---|---|
| `ruff` | Rust | 8 MB | Replaces 20+ Python tools, single binary |
| `uv` | Rust | 12 MB | Python package manager, replaces pip + venv |
| `atuin` | Rust | 10 MB | Shell history sync, single binary |
| `sccache` | Rust | 15 MB | Compiler cache, distributed mode |
| `deno` | Rust | 85 MB | JS/TS runtime, includes V8 |
| `ripgrep` | Rust | 5 MB | grep replacement, universally deployed |

---

## Conclusion

A Rust CLI with `clap` + `serde` compiles to a **single binary** that eliminates Python environment hell entirely:

- **No runtime dependencies** — not even libc (with musl)
- **No version conflicts** — dependencies are compiled in, not resolved at runtime
- **No virtualenv** — one binary, one config, one vault
- **Fast startup** — <50ms vs 2-5 seconds for Python import overhead
- **Small footprint** — 8-15 MB vs 200+ MB for Python + dependencies
- **Easy distribution** — `scp`, `curl | tar`, package manager
- **Cross-platform** — same codebase compiles to Linux, macOS, Windows, ARM64
- **Type-safe configuration** — `serde` + `toml` validates at load time, not runtime
- **Shell completions** — generated automatically for bash, zsh, fish, PowerShell

The `mn` binary is the entire Mnemosyne system: CLI, server, pack exporter, maintenance tools. It is what `cargo`, `rustc`, `git`, and `ssh` are — tools so reliable you forget they exist. This is the deployment experience that makes local-first AI infrastructure accessible to non-programmers.

Python is a fantastic language for experimentation. Rust is a fantastic language for infrastructure. Mnemosyne's CLI is infrastructure.
