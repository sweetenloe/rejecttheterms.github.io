"""Tkinter article uploader for the Reject the Terms static site.

This utility stages a new article page, copies selected assets, builds a preview
copy of the site, and only writes to the live site when Apply is pressed.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from dataclasses import dataclass, field
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    TOP,
    Button,
    Entry,
    Frame,
    Label,
    LabelFrame,
    Listbox,
    Menu,
    StringVar,
    Text,
    Tk,
    filedialog,
    messagebox,
    ttk,
)


APP_TITLE = "Reject the Terms Article Uploader"
WORK_DIR = ".article-uploader-work"
BACKUP_DIR = ".site-backups"
SITE_OVERLAY_DIR = "site"
ARTICLES_FILE = "articles.html"


@dataclass
class InlineAsset:
    source: Path
    alt: str = ""

    @property
    def original_name(self) -> str:
        return self.source.name


@dataclass
class ArticleDraft:
    title: str
    category: str
    summary: str
    description: str
    footer_note: str
    slug: str
    cover_source: Path
    body: str
    inline_assets: list[InlineAsset] = field(default_factory=list)


def site_root() -> Path:
    return Path(__file__).resolve().parent


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "new-article"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find a unique path for {path.name}")


def clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def make_backup(root: Path, label: str) -> Path:
    backup_dir = root / BACKUP_DIR
    backup_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    archive = unique_path(backup_dir / f"rejecttheterms-{label}-{stamp}.zip")
    skip_dirs = {".git", BACKUP_DIR, WORK_DIR}
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in root.rglob("*"):
            rel = item.relative_to(root)
            if rel.parts and rel.parts[0] in skip_dirs:
                continue
            if item.is_file():
                zf.write(item, rel.as_posix())
    return archive


def copy_site_for_preview(root: Path, destination: Path) -> None:
    clean_dir(destination)
    skip_dirs = {".git", BACKUP_DIR, WORK_DIR}
    for item in root.iterdir():
        if item.name in skip_dirs:
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        elif item.is_file():
            shutil.copy2(item, target)


def copy_asset(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = unique_path(destination)
    shutil.copy2(source, target)
    return target


def render_image_token(token: str, asset_map: dict[str, tuple[str, str]], as_figure: bool) -> str:
    match = re.fullmatch(r"\[\[image:([^|\]]+)(?:\|([^\]]+))?\]\]", token.strip())
    if not match:
        return html.escape(token)
    name = match.group(1).strip()
    alt = match.group(2).strip() if match.group(2) else ""
    src, default_alt = asset_map.get(name, ("", ""))
    if not src:
        return html.escape(token)
    final_alt = html.escape(alt or default_alt or name)
    image = f'<img src="{html.escape(src, quote=True)}" alt="{final_alt}">'
    if as_figure:
        return f"<figure>{image}<figcaption>{final_alt}</figcaption></figure>"
    return image


def render_inline(text: str, asset_map: dict[str, tuple[str, str]]) -> str:
    escaped = html.escape(text)

    def image_token(match: re.Match[str]) -> str:
        return render_image_token(html.unescape(match.group(0)), asset_map, as_figure=False)

    escaped = re.sub(r"\[\[image:([^|\]]+)(?:\|([^\]]+))?\]\]", image_token, escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)

    def link_token(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        href = html.escape(match.group(2), quote=True)
        return f'<a href="{href}" target="_blank" rel="noopener noreferrer">{label}</a>'

    escaped = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", link_token, escaped)
    return escaped


def markdown_to_html(markdown: str, asset_map: dict[str, tuple[str, str]]) -> str:
    lines = markdown.replace("\r\n", "\n").split("\n")
    output: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    quote_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = " ".join(line.strip() for line in paragraph)
            output.append(f"        <p>{render_inline(text, asset_map)}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            output.append("        <ul>")
            for item in list_items:
                output.append(f"          <li>{render_inline(item, asset_map)}</li>")
            output.append("        </ul>")
            list_items = []

    def flush_quote() -> None:
        nonlocal quote_lines
        if quote_lines:
            text = " ".join(line.strip() for line in quote_lines)
            output.append(f"        <blockquote>{render_inline(text, asset_map)}</blockquote>")
            quote_lines = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            flush_quote()
            continue
        if re.fullmatch(r"\[\[image:([^|\]]+)(?:\|([^\]]+))?\]\]", stripped):
            flush_paragraph()
            flush_list()
            flush_quote()
            output.append(f"        {render_image_token(stripped, asset_map, as_figure=True)}")
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            flush_list()
            flush_quote()
            output.append(f"        <h4>{render_inline(stripped[4:], asset_map)}</h4>")
        elif stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            flush_quote()
            output.append(f"        <h3>{render_inline(stripped[3:], asset_map)}</h3>")
        elif stripped.startswith("# "):
            flush_paragraph()
            flush_list()
            flush_quote()
            output.append(f"        <h2>{render_inline(stripped[2:], asset_map)}</h2>")
        elif stripped.startswith("> "):
            flush_paragraph()
            flush_list()
            quote_lines.append(stripped[2:])
        elif stripped.startswith(("- ", "* ")):
            flush_paragraph()
            flush_quote()
            list_items.append(stripped[2:])
        elif stripped == "---":
            flush_paragraph()
            flush_list()
            flush_quote()
            output.append("        <hr>")
        else:
            flush_list()
            flush_quote()
            paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    flush_quote()
    return "\n\n".join(output) or "        <p></p>"


def build_article_html(draft: ArticleDraft, cover_relative: str, body_html: str) -> str:
    title = html.escape(draft.title)
    category = html.escape(draft.category)
    summary = html.escape(draft.summary)
    description = html.escape(draft.description or draft.summary, quote=True)
    footer_note = html.escape(draft.footer_note or draft.category)
    cover = html.escape(cover_relative, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title} | Reject the Terms</title>
  <meta name="description" content="{description}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>

  <header class="site-header">
    <div class="container site-header__inner">
      <a class="brand" href="index.html" aria-label="Reject the Terms home">
        <span class="brand__name">Reject the Terms</span>
        <span class="brand__sub">RejectTheTerms.com</span>
      </a>

      <button class="nav-toggle" type="button" aria-label="Open navigation">Menu</button>

      <nav class="site-nav" aria-label="Primary navigation">
        <ul>
          <li><a href="index.html">Home</a></li>
          <li><a href="articles.html">Articles</a></li>
        </ul>
      </nav>
    </div>
  </header>

  <main id="main">
    <section class="article-hero" style="--article-image: url('{cover}');">
      <div class="container article-hero__inner">
        <p class="article-meta">{category}</p>
        <h1>{title}</h1>
        <p class="article-dek">{summary}</p>
      </div>
    </section>

    <article class="article-layout">
      <div class="reading-container">
        <a class="article-back-link" href="articles.html">&larr; Back to articles</a>

{body_html}
      </div>
    </article>
  </main>

  <footer class="site-footer">
    <div class="container site-footer__inner">
      <p>Reject the Terms</p>
      <p>{footer_note}</p>
    </div>
  </footer>
</body>
</html>
"""


def make_article_row(draft: ArticleDraft, article_file: str, cover_relative: str) -> str:
    title = html.escape(draft.title)
    category = html.escape(draft.category)
    summary = html.escape(draft.summary)
    article_href = html.escape(article_file, quote=True)
    cover = html.escape(cover_relative, quote=True)
    alt = html.escape(f"Cover art for {draft.title}", quote=True)
    return (
        f'          <article class="article-row"><a class="article-row__thumb" href="{article_href}">'
        f'<img src="{cover}" alt="{alt}"></a><div class="article-row__body">'
        f'<p class="article-meta">{category}</p><h2 class="article-row__title">'
        f'<a href="{article_href}">{title}</a></h2><p class="article-row__summary">{summary}</p>'
        f'<a class="text-link" href="{article_href}">Read article</a></div></article>'
    )


def insert_article_row(articles_html: str, row: str) -> str:
    marker = '<div class="article-list">'
    index = articles_html.find(marker)
    if index == -1:
        raise RuntimeError("Could not find the article list in articles.html.")
    insert_at = index + len(marker)
    return articles_html[:insert_at] + "\n" + row + articles_html[insert_at:]


class PreviewServer:
    def __init__(self) -> None:
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self, directory: Path, page: str = "articles.html") -> str:
        self.stop()

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(directory), **kwargs)

            def log_message(self, format: str, *args) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{port}/{page}"

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        self.thread = None


class ArticleUploaderApp:
    def __init__(self, root_window: Tk) -> None:
        self.root = site_root()
        self.window = root_window
        self.window.title(APP_TITLE)
        self.window.geometry("1080x760")
        self.window.minsize(920, 640)

        self.title_var = StringVar()
        self.category_var = StringVar(value="Privacy / technology")
        self.summary_var = StringVar()
        self.description_var = StringVar()
        self.footer_var = StringVar()
        self.slug_var = StringVar()
        self.cover_var = StringVar()
        self.status_var = StringVar(value="Build a stage first. Nothing has been applied to the live site.")
        self.inline_assets: list[InlineAsset] = []
        self.last_stage: Path | None = None
        self.preview_site: Path | None = None
        self.preview_server = PreviewServer()

        self._build_ui()
        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self) -> None:
        top = Frame(self.window, padx=12, pady=12)
        top.pack(side=TOP, fill=BOTH, expand=True)

        details = LabelFrame(top, text="Article details", padx=10, pady=10)
        details.pack(side=TOP, fill="x")
        self._field(details, "Title", self.title_var, 0)
        self._field(details, "Category", self.category_var, 1)
        self._field(details, "Summary/dek", self.summary_var, 2)
        self._field(details, "Meta description", self.description_var, 3)
        self._field(details, "Footer note", self.footer_var, 4)
        self._field(details, "Slug", self.slug_var, 5)
        Button(details, text="Use title as slug", command=self.set_slug_from_title).grid(row=5, column=2, padx=6, sticky="ew")

        asset_frame = Frame(top)
        asset_frame.pack(side=TOP, fill="x", pady=(10, 0))
        cover = LabelFrame(asset_frame, text="Cover art", padx=10, pady=10)
        cover.pack(side=LEFT, fill="both", expand=True, padx=(0, 5))
        Entry(cover, textvariable=self.cover_var).pack(side=LEFT, fill="x", expand=True)
        Button(cover, text="Choose cover", command=self.choose_cover).pack(side=RIGHT, padx=(8, 0))

        inline = LabelFrame(asset_frame, text="Inline photos", padx=10, pady=10)
        inline.pack(side=RIGHT, fill="both", expand=True, padx=(5, 0))
        self.inline_list = Listbox(inline, height=4)
        self.inline_list.pack(side=LEFT, fill="both", expand=True)
        inline_buttons = Frame(inline)
        inline_buttons.pack(side=RIGHT, fill="y", padx=(8, 0))
        Button(inline_buttons, text="Add photos", command=self.add_inline_assets).pack(fill="x")
        Button(inline_buttons, text="Remove", command=self.remove_inline_asset).pack(fill="x", pady=(5, 0))
        Button(inline_buttons, text="Insert token", command=self.insert_image_token).pack(fill="x", pady=(5, 0))

        body_frame = LabelFrame(top, text="Article body", padx=10, pady=10)
        body_frame.pack(side=TOP, fill=BOTH, expand=True, pady=(10, 0))
        toolbar = Frame(body_frame)
        toolbar.pack(side=TOP, fill="x", pady=(0, 6))
        Button(toolbar, text="Load .txt/.md/.html", command=self.load_body_file).pack(side=LEFT)
        Label(
            toolbar,
            text="Supports paragraphs, # headings, - bullets, > quotes, --- rules, **bold**, *italic*, links, and [[image:file.jpg|Alt]].",
        ).pack(side=LEFT, padx=10)
        self.body_text = Text(body_frame, wrap="word", undo=True)
        self.body_text.pack(fill=BOTH, expand=True)

        actions = Frame(top)
        actions.pack(side=TOP, fill="x", pady=(10, 0))
        Button(actions, text="Build staged article", command=self.build_stage).pack(side=LEFT)
        Button(actions, text="Preview post", command=self.preview_post).pack(side=LEFT, padx=(8, 0))
        Button(actions, text="Preview articles page", command=self.preview_articles_page).pack(side=LEFT, padx=(8, 0))
        Button(actions, text="Apply to live site", command=self.apply_stage).pack(side=LEFT, padx=(8, 0))
        Button(actions, text="Open staging folder", command=self.open_staging_folder).pack(side=LEFT, padx=(8, 0))
        Label(actions, textvariable=self.status_var, anchor="w").pack(side=LEFT, fill="x", expand=True, padx=(12, 0))

        menu = Menu(self.window)
        file_menu = Menu(menu, tearoff=0)
        file_menu.add_command(label="Make backup now", command=self.backup_now)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close)
        menu.add_cascade(label="File", menu=file_menu)
        self.window.config(menu=menu)

    def _field(self, parent: Frame, label: str, var: StringVar, row: int) -> None:
        Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=2, padx=(8, 0))
        parent.columnconfigure(1, weight=1)

    def set_slug_from_title(self) -> None:
        self.slug_var.set(slugify(self.title_var.get()))

    def choose_cover(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Choose cover art",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp *.gif"), ("All files", "*.*")],
        )
        if file_path:
            self.cover_var.set(file_path)

    def add_inline_assets(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Choose inline photos",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp *.gif"), ("All files", "*.*")],
        )
        for file_path in paths:
            path = Path(file_path)
            if path.exists():
                self.inline_assets.append(InlineAsset(source=path, alt=path.stem.replace("-", " ").replace("_", " ")))
        self.refresh_inline_list()

    def remove_inline_asset(self) -> None:
        selected = list(self.inline_list.curselection())
        for index in reversed(selected):
            del self.inline_assets[index]
        self.refresh_inline_list()

    def refresh_inline_list(self) -> None:
        self.inline_list.delete(0, END)
        for asset in self.inline_assets:
            self.inline_list.insert(END, asset.original_name)

    def insert_image_token(self) -> None:
        selected = self.inline_list.curselection()
        if not selected:
            messagebox.showinfo(APP_TITLE, "Select an inline photo first.")
            return
        asset = self.inline_assets[selected[0]]
        token = f"[[image:{asset.original_name}|{asset.alt}]]"
        self.body_text.insert("insert", token)
        self.body_text.focus_set()

    def load_body_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Load article body",
            filetypes=[("Text and HTML", "*.txt *.md *.markdown *.html *.htm"), ("All files", "*.*")],
        )
        if not file_path:
            return
        text = Path(file_path).read_text(encoding="utf-8")
        self.body_text.delete("1.0", END)
        self.body_text.insert("1.0", text)

    def draft_from_form(self) -> ArticleDraft:
        title = self.title_var.get().strip()
        if not title:
            raise ValueError("Title is required.")
        category = self.category_var.get().strip() or "Article"
        summary = self.summary_var.get().strip()
        if not summary:
            raise ValueError("Summary/dek is required.")
        cover = Path(self.cover_var.get().strip())
        if not cover.is_file():
            raise ValueError("Choose a valid cover image.")
        slug = slugify(self.slug_var.get() or title)
        body = self.body_text.get("1.0", END).strip()
        if not body:
            raise ValueError("Article body is required.")
        return ArticleDraft(
            title=title,
            category=category,
            summary=summary,
            description=self.description_var.get().strip(),
            footer_note=self.footer_var.get().strip(),
            slug=slug,
            cover_source=cover,
            body=body,
            inline_assets=list(self.inline_assets),
        )

    def build_stage(self) -> None:
        try:
            draft = self.draft_from_form()
            stage = self.root / WORK_DIR / "staged"
            clean_dir(stage)
            overlay = stage / SITE_OVERLAY_DIR
            images = overlay / "images"
            images.mkdir(parents=True, exist_ok=True)

            cover_name = f"{draft.slug}-cover{draft.cover_source.suffix.lower()}"
            cover_target = copy_asset(draft.cover_source, images / cover_name)
            cover_relative = f"images/{cover_target.name}"

            asset_map: dict[str, tuple[str, str]] = {}
            manifest_assets = [{"kind": "cover", "source": str(draft.cover_source), "site_path": cover_relative}]
            for index, asset in enumerate(draft.inline_assets, start=1):
                clean_name = slugify(asset.source.stem)
                target_name = f"{draft.slug}-{index:02d}-{clean_name}{asset.source.suffix.lower()}"
                target = copy_asset(asset.source, images / target_name)
                relative = f"images/{target.name}"
                asset_map[asset.original_name] = (relative, asset.alt)
                asset_map[target.name] = (relative, asset.alt)
                manifest_assets.append({"kind": "inline", "source": str(asset.source), "site_path": relative})

            body_html = markdown_to_html(draft.body, asset_map)
            article_file = f"article-{draft.slug}.html"
            (overlay / article_file).write_text(build_article_html(draft, cover_relative, body_html), encoding="utf-8", newline="\n")

            current_articles = (self.root / ARTICLES_FILE).read_text(encoding="utf-8")
            row = make_article_row(draft, article_file, cover_relative)
            (overlay / ARTICLES_FILE).write_text(insert_article_row(current_articles, row), encoding="utf-8", newline="\n")
            manifest = {
                "title": draft.title,
                "slug": draft.slug,
                "article_file": article_file,
                "articles_file": ARTICLES_FILE,
                "assets": manifest_assets,
                "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            self.last_stage = stage
            self.status_var.set(f"Staged {article_file}. Preview before applying.")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def prepare_preview_site(self) -> Path | None:
        if not self.last_stage:
            self.build_stage()
            if not self.last_stage:
                return None
        preview_site = self.root / WORK_DIR / "preview-site"
        copy_site_for_preview(self.root, preview_site)
        overlay = self.last_stage / SITE_OVERLAY_DIR
        self.copy_overlay(overlay, preview_site)
        self.preview_site = preview_site
        return preview_site

    def preview_post(self) -> None:
        try:
            preview_site = self.prepare_preview_site()
            if not preview_site or not self.last_stage:
                return
            manifest_path = self.last_stage / "manifest.json"
            if not manifest_path.exists():
                messagebox.showerror(APP_TITLE, "The staged manifest is missing. Rebuild the stage.")
                return
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            article_file = manifest["article_file"]
            url = self.preview_server.start(preview_site, article_file)
            webbrowser.open(url)
            self.status_var.set(f"Post preview running at {url}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def preview_articles_page(self) -> None:
        try:
            preview_site = self.prepare_preview_site()
            if not preview_site:
                return
            url = self.preview_server.start(preview_site, ARTICLES_FILE)
            webbrowser.open(url)
            self.status_var.set(f"Articles page preview running at {url}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def apply_stage(self) -> None:
        if not self.last_stage:
            messagebox.showinfo(APP_TITLE, "Build and preview the staged article first.")
            return
        manifest_path = self.last_stage / "manifest.json"
        if not manifest_path.exists():
            messagebox.showerror(APP_TITLE, "The staged manifest is missing. Rebuild the stage.")
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        article_file = manifest["article_file"]
        if (self.root / article_file).exists():
            messagebox.showerror(APP_TITLE, f"{article_file} already exists in the live site. Change the slug and rebuild.")
            return
        confirmed = messagebox.askyesno(
            APP_TITLE,
            "This will create a fresh backup, copy the staged article/assets into the site, "
            "and update articles.html so the new article appears first. Continue?",
        )
        if not confirmed:
            return
        try:
            backup = make_backup(self.root, "pre-apply")
            self.copy_overlay(self.last_stage / SITE_OVERLAY_DIR, self.root)
            self.status_var.set(f"Applied {article_file}. Backup: {backup.name}")
            messagebox.showinfo(APP_TITLE, f"Applied {article_file}.\nBackup saved at:\n{backup}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def copy_overlay(self, overlay: Path, destination: Path) -> None:
        for item in overlay.rglob("*"):
            rel = item.relative_to(overlay)
            target = destination / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)

    def backup_now(self) -> None:
        try:
            backup = make_backup(self.root, "manual")
            self.status_var.set(f"Backup created: {backup.name}")
            messagebox.showinfo(APP_TITLE, f"Backup saved at:\n{backup}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def open_staging_folder(self) -> None:
        path = self.root / WORK_DIR
        path.mkdir(exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def close(self) -> None:
        self.preview_server.stop()
        self.window.destroy()


def main() -> None:
    root = Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    app = ArticleUploaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
