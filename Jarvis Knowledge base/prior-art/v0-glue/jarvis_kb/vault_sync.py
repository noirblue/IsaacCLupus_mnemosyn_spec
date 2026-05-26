import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import frontmatter


class VaultSync:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.foundry = cfg["foundry"]
        self.frontline = cfg["frontline"]
        self.strategy = cfg["sync"]["strategy"]

    def run(self) -> None:
        print("[sync] Starting publish pipeline...")
        self._ensure_dirs()

        # 1. Pull compiled artifacts from Foundry
        self._sync_synto()
        self._sync_synthadoc()

        # 2. Fix cross-tool metadata collisions
        self._normalize_unified_vault()

        # 3. Rebuild frontline search indexes
        self._rebuild_llm_wiki_index()

        # 4. Tell Link to load the new state
        self._link_load_latest()

        # 5. Atomic commit if using git
        if self.strategy == "git":
            self._git_commit()

        print("[sync] Publish complete.")

    def _ensure_dirs(self) -> None:
        for key in ["unified_vault", "llm_wiki_vault"]:
            Path(self.frontline[key]).mkdir(parents=True, exist_ok=True)

    def _normalize_frontmatter(self, src: Path, dst: Path, source_tool: str) -> None:
        post = frontmatter.load(src)

        # Normalize confidence → maturity
        confidence = post.metadata.pop("confidence", None)
        status = post.metadata.pop("status", None)
        if isinstance(confidence, (int, float)):
            maturity = "established" if confidence > 0.8 else "refining" if confidence > 0.5 else "seed"
        elif status == "contradicted":
            maturity = "disputed"
        else:
            maturity = post.metadata.get("maturity", "seed")

        # Build normalized metadata
        clean = {
            "title": post.metadata.get("title", src.stem.replace("_", " ").title()),
            "maturity": maturity,
            "source_tool": source_tool,
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "provenance": post.metadata.get("provenance") or post.metadata.get("source"),
        }

        # Preserve citations if present (Synthadoc style)
        if "citations" in post.metadata:
            clean["citations"] = post.metadata["citations"]

        # Strip tool-specific internal keys that clash across tools
        for key in ["compile_run_id", "audit_hash", "olw_id", "synto_version"]:
            post.metadata.pop(key, None)

        post.metadata = clean
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(frontmatter.dumps(post), encoding="utf-8")

    def _sync_synto(self) -> None:
        src = Path(self.foundry["synto_vault"]) / "wiki"
        dst = Path(self.frontline["unified_vault"]) / "self"
        if not src.exists():
            print("[sync] Synto wiki not found, skipping.")
            return
        for md in src.rglob("*.md"):
            # Skip drafts unless explicitly approved
            if ".drafts" in md.parts:
                continue
            rel = md.relative_to(src)
            self._normalize_frontmatter(md, dst / rel, "synto")

    def _sync_synthadoc(self) -> None:
        src = Path(self.foundry["synthadoc_vault"]) / "wiki"
        dst = Path(self.frontline["unified_vault"]) / "world"
        if not src.exists():
            print("[sync] Synthadoc wiki not found, skipping.")
            return
        for md in src.rglob("*.md"):
            rel = md.relative_to(src)
            self._normalize_frontmatter(md, dst / rel, "synthadoc")

    def _normalize_unified_vault(self) -> None:
        """Resolve filename collisions between self/ and world/."""
        unified = Path(self.frontline["unified_vault"])
        world = unified / "world"
        self_dir = unified / "self"
        if not world.exists() or not self_dir.exists():
            return
        for wpath in world.rglob("*.md"):
            spath = self_dir / wpath.relative_to(world)
            if spath.exists():
                # Prefer self-knowledge over world-knowledge for same-named concepts
                # by renaming the world copy with a suffix
                new_name = wpath.with_name(f"{wpath.stem}_ext{wpath.suffix}")
                wpath.rename(new_name)
                print(f"[sync] Resolved collision: {spath.name} -> preferring self/")

    def _rebuild_llm_wiki_index(self) -> None:
        vault = Path(self.frontline["llm_wiki_vault"])
        unified = Path(self.frontline["unified_vault"])

        # LLM-WIKI-MCP intentionally skips its own vault dir during ingest-dir
        subprocess.run(
            ["llm-wiki", "--vault", str(vault), "ingest-dir", str(unified)],
            check=False,
        )
        subprocess.run(
            ["llm-wiki", "--vault", str(vault), "reindex"],
            check=False,
        )
        print("[sync] LLM-WIKI-MCP index rebuilt.")

    def _link_load_latest(self) -> None:
        tag = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        vault = self.frontline["link_vault"]
        # Best-effort: Link may not have snapshot CLI; adjust to your Link version
        for cmd in [
            ["link", "wiki", "snapshot", "--tag", tag, "--vault", vault],
            ["link", "wiki", "load-snapshot", tag, "--vault", vault],
        ]:
            subprocess.run(cmd, check=False)
        print("[sync] Link snapshot updated.")

    def _git_commit(self) -> None:
        unified = Path(self.frontline["unified_vault"])
        if not (unified / ".git").exists():
            subprocess.run(["git", "-C", str(unified), "init"], check=False)
        subprocess.run(["git", "-C", str(unified), "add", "."], check=False)
        subprocess.run(
            ["git", "-C", str(unified), "commit", "-m", f"publish: {datetime.now(timezone.utc).isoformat()}"],
            check=False,
        )
