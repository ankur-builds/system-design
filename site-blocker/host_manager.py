#!/usr/bin/env python3

import os
import sys
import socket
import shutil
import subprocess
import platform
import re
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from urllib.parse import urlparse


HOSTS_FILE = "/etc/hosts"


# ─────────────────────────────────────────────────────────────
# Privileges
# ─────────────────────────────────────────────────────────────

def ensure_root():
    if os.name == "nt":
        return

    if os.geteuid() == 0:
        return

    print("Requesting administrator privileges...")

    try:
        subprocess.run(
            ["sudo", sys.executable, os.path.abspath(__file__)],
            check=True
        )
    except subprocess.CalledProcessError:
        sys.exit("Unable to obtain administrator privileges.")

    sys.exit(0)


# ─────────────────────────────────────────────────────────────
# Domain handling
# ─────────────────────────────────────────────────────────────

def normalize_source(value):
    value = value.strip()

    if not value:
        return ""

    # Accept:
    # www.example.com
    # https://www.example.com/path?a=1
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.hostname or ""

    else:
        # Remove accidental path/query fragments.
        value = value.split("/")[0]
        value = value.split("?")[0]
        value = value.split("#")[0]

    value = value.lower().strip(".")

    if not re.match(
        r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
        value,
    ):
        raise ValueError(f"Invalid source hostname: {value}")

    return value


def resolve_destination(value):
    value = value.strip()

    if not value:
        raise ValueError("Destination cannot be empty.")

    # Already an IPv4 address.
    try:
        socket.inet_aton(value)
        return value
    except OSError:
        pass

    # IPv6.
    try:
        socket.inet_pton(socket.AF_INET6, value)
        return value
    except OSError:
        pass

    hostname = normalize_source(value)

    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        raise ValueError(
            f"Could not resolve destination: {hostname}"
        )


# ─────────────────────────────────────────────────────────────
# DNS cache
# ─────────────────────────────────────────────────────────────

def flush_dns():
    system = platform.system()

    commands = []

    if system == "Darwin":
        commands = [
            ["dscacheutil", "-flushcache"],
            ["killall", "-HUP", "mDNSResponder"],
        ]

    elif system == "Linux":
        commands = [
            ["resolvectl", "flush-caches"],
            ["systemd-resolve", "--flush-caches"],
        ]

    elif system == "Windows":
        commands = [["ipconfig", "/flushdns"]]

    for command in commands:
        try:
            subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return True
        except FileNotFoundError:
            continue

    return False


# ─────────────────────────────────────────────────────────────
# Hosts file
# ─────────────────────────────────────────────────────────────

def backup_hosts():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{HOSTS_FILE}.backup_{timestamp}"

    shutil.copy2(HOSTS_FILE, backup)

    return backup


def update_hosts(comment, mappings):
    with open(HOSTS_FILE, "r", encoding="utf-8") as f:
        existing = f.read()

    existing_hosts = set()

    for line in existing.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        parts = stripped.split()

        if len(parts) >= 2:
            for hostname in parts[1:]:
                existing_hosts.add(hostname.lower())

    new_lines = [
        "",
        f"# {comment}",
    ]

    for ip, source in mappings:
        if source.lower() in existing_hosts:
            raise ValueError(
                f"{source} already exists in /etc/hosts."
            )

        new_lines.append(f"{ip:<40} {source}")

    new_lines.append("")

    with open(HOSTS_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(new_lines))

    return True


# ─────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────

class HostsManager:

    def __init__(self, root):
        self.root = root
        self.root.title("Hosts File Manager")
        self.root.geometry("920x720")
        self.root.minsize(760, 600)

        self.rows = []

        self.setup_style()
        self.build_ui()
        self.add_row()
        self.update_preview()

    def setup_style(self):
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "TFrame",
            background="#f5f7fb"
        )

        style.configure(
            "Card.TFrame",
            background="#ffffff"
        )

        style.configure(
            "Title.TLabel",
            background="#f5f7fb",
            foreground="#111827",
            font=("Helvetica", 27, "bold")
        )

        style.configure(
            "Subtitle.TLabel",
            background="#f5f7fb",
            foreground="#6b7280",
            font=("Helvetica", 11)
        )

        style.configure(
            "Section.TLabel",
            background="#ffffff",
            foreground="#111827",
            font=("Helvetica", 12, "bold")
        )

        style.configure(
            "TLabel",
            background="#ffffff",
            foreground="#374151",
            font=("Helvetica", 10)
        )

        style.configure(
            "TEntry",
            padding=10,
            font=("Helvetica", 11)
        )

        style.configure(
            "Primary.TButton",
            padding=12,
            font=("Helvetica", 11, "bold")
        )

        style.configure(
            "Secondary.TButton",
            padding=8,
            font=("Helvetica", 10)
        )

    def build_ui(self):

        outer = ttk.Frame(self.root, padding=32)
        outer.pack(fill="both", expand=True)

        # Header
        ttk.Label(
            outer,
            text="Hosts File Manager",
            style="Title.TLabel"
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text="Minimal domain mapping console",
            style="Subtitle.TLabel"
        ).pack(anchor="w", pady=(2, 25))

        # Comment card
        comment_card = ttk.Frame(
            outer,
            style="Card.TFrame",
            padding=20
        )
        comment_card.pack(fill="x", pady=(0, 14))

        ttk.Label(
            comment_card,
            text="COMMENT  *",
            style="Section.TLabel"
        ).pack(anchor="w")

        self.comment = ttk.Entry(comment_card)
        self.comment.pack(fill="x", pady=(10, 0))

        # Mapping card
        mapping_card = ttk.Frame(
            outer,
            style="Card.TFrame",
            padding=20
        )
        mapping_card.pack(fill="both", expand=True, pady=(0, 14))

        header = ttk.Frame(mapping_card)
        header.pack(fill="x", pady=(0, 12))

        ttk.Label(
            header,
            text="DOMAIN MAPPINGS",
            style="Section.TLabel"
        ).pack(side="left")

        ttk.Button(
            header,
            text="+  Add Mapping",
            command=self.add_row,
            style="Secondary.TButton"
        ).pack(side="right")

        # Column headings
        headings = ttk.Frame(mapping_card)
        headings.pack(fill="x")

        ttk.Label(
            headings,
            text="SOURCE"
        ).grid(row=0, column=0, sticky="w", padx=5)

        ttk.Label(
            headings,
            text="DESTINATION"
        ).grid(row=0, column=1, sticky="w", padx=5)

        headings.columnconfigure(0, weight=1)
        headings.columnconfigure(1, weight=1)

        self.rows_frame = ttk.Frame(mapping_card)
        self.rows_frame.pack(fill="x", pady=6)

        self.rows_frame.columnconfigure(0, weight=1)
        self.rows_frame.columnconfigure(1, weight=1)

        # Preview
        preview_card = ttk.Frame(
            outer,
            style="Card.TFrame",
            padding=20
        )
        preview_card.pack(fill="x", pady=(0, 14))

        ttk.Label(
            preview_card,
            text="PREVIEW",
            style="Section.TLabel"
        ).pack(anchor="w")

        self.preview = tk.Text(
            preview_card,
            height=7,
            bg="#111827",
            fg="#d1fae5",
            insertbackground="white",
            relief="flat",
            padx=14,
            pady=12,
            font=("Courier", 10)
        )
        self.preview.pack(fill="x", pady=(10, 0))
        self.preview.configure(state="disabled")

        # Bottom
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x")

        self.status = ttk.Label(
            bottom,
            text="● Ready",
            foreground="#059669"
        )
        self.status.pack(side="left")

        ttk.Button(
            bottom,
            text="UPDATE /etc/hosts",
            command=self.submit,
            style="Primary.TButton"
        ).pack(side="right")

    def add_row(self):
        index = len(self.rows)

        source = ttk.Entry(self.rows_frame)
        destination = ttk.Entry(self.rows_frame)

        source.grid(
            row=index,
            column=0,
            sticky="ew",
            padx=5,
            pady=5
        )

        destination.grid(
            row=index,
            column=1,
            sticky="ew",
            padx=5,
            pady=5
        )

        delete = ttk.Button(
            self.rows_frame,
            text="×",
            width=3,
            command=lambda: self.remove_row(index)
        )

        delete.grid(
            row=index,
            column=2,
            padx=(5, 0),
            pady=5
        )

        source.bind("<KeyRelease>", lambda e: self.update_preview())
        destination.bind("<KeyRelease>", lambda e: self.update_preview())

        self.rows.append(
            (source, destination, delete)
        )

        self.update_preview()

    def remove_row(self, index):
        if len(self.rows) == 1:
            return

        source, destination, delete = self.rows[index]

        source.destroy()
        destination.destroy()
        delete.destroy()

        del self.rows[index]

        # Rebuild row positions.
        for i, (src, dst, btn) in enumerate(self.rows):
            src.grid_configure(row=i)
            dst.grid_configure(row=i)
            btn.grid_configure(row=i)

        self.update_preview()

    def collect(self):
        mappings = []

        for source_entry, destination_entry, _ in self.rows:
            source = source_entry.get().strip()
            destination = destination_entry.get().strip()

            if not source and not destination:
                continue

            if not source or not destination:
                raise ValueError(
                    "Every mapping needs both source and destination."
                )

            source = normalize_source(source)
            ip = resolve_destination(destination)

            mappings.append((ip, source))

        if not mappings:
            raise ValueError("Add at least one mapping.")

        return mappings

    def update_preview(self):
        try:
            mappings = self.collect()

            lines = [
                f"# {self.comment.get().strip() or 'your comment'}"
            ]

            for ip, source in mappings:
                lines.append(
                    f"{ip:<40} {source}"
                )

            preview = "\n".join(lines)

        except Exception:
            preview = "# Complete the mapping fields..."

        self.preview.configure(state="normal")
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", preview)
        self.preview.configure(state="disabled")

    def submit(self):

        comment = self.comment.get().strip()

        if not comment:
            messagebox.showwarning(
                "Comment required",
                "Please enter a comment."
            )
            self.comment.focus()
            return

        try:
            mappings = self.collect()

            # Confirmation
            names = "\n".join(
                f"  {ip}  ←  {source}"
                for ip, source in mappings
            )

            confirm = messagebox.askyesno(
                "Update /etc/hosts?",
                f"These entries will be added:\n\n"
                f"{names}\n\n"
                f"Comment:\n# {comment}\n\n"
                f"A backup will be created first."
            )

            if not confirm:
                return

            backup = backup_hosts()

            update_hosts(
                comment,
                mappings
            )

            flushed = flush_dns()

            self.status.configure(
                text="● Updated successfully",
                foreground="#059669"
            )

            dns_message = (
                "DNS cache flushed."
                if flushed
                else "DNS cache flush command unavailable."
            )

            messagebox.showinfo(
                "Success",
                f"/etc/hosts updated successfully.\n\n"
                f"Backup:\n{backup}\n\n"
                f"{dns_message}"
            )

        except Exception as e:

            self.status.configure(
                text="● Update failed",
                foreground="#dc2626"
            )

            messagebox.showerror(
                "Update failed",
                str(e)
            )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ensure_root()

    root = tk.Tk()

    app = HostsManager(root)

    root.mainloop()
