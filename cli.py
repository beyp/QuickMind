#!/usr/bin/env python
"""
QuickMind CLI - Interface ligne de commande
Usage: python cli.py [COMMAND] [OPTIONS]
"""
import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich import box
from datetime import datetime
from core.database import (init_db, get_tasks, get_categories,
                           add_task, update_task, delete_task,
                           add_category, get_pending_reminders)
from core.file_handler import save_attachment

app  = typer.Typer(help="QuickMind - Gestionnaire de taches", add_completion=False)
cons = Console()


def _ensure_db():
    init_db()


# ── ADD ───────────────────────────────────────────────────────────────────────
@app.command("add")
def cli_add(
    title:  str            = typer.Argument(..., help="Titre de la tache"),
    cat:    Optional[str]  = typer.Option(None,      "--cat",    "-c", help="Nom de categorie"),
    prio:   Optional[str]  = typer.Option("normal",  "--prio",   "-p", help="low|normal|high|urgent"),
    remind: Optional[str]  = typer.Option(None,      "--remind", "-r", help="JJ/MM/AAAA HH:MM"),
    desc:   Optional[str]  = typer.Option("",        "--desc",   "-d", help="Description"),
    file:   Optional[str]  = typer.Option(None,      "--file",   "-f", help="Chemin fichier joint"),
):
    """Ajouter une nouvelle tache."""
    _ensure_db()
    cats = {c.name.lower(): c.id for c in get_categories()}
    cat_id = cats.get((cat or "").lower())

    remind_dt = None
    if remind:
        try:
            remind_dt = datetime.strptime(remind, "%d/%m/%Y %H:%M")
        except ValueError:
            cons.print("[red]Format de rappel invalide. Utilisez JJ/MM/AAAA HH:MM[/red]")
            raise typer.Exit(1)

    task = add_task(
        title=title,
        description=desc or "",
        category_id=cat_id,
        priority=prio or "normal",
        reminder_at=remind_dt,
    )

    if file:
        new_path = save_attachment(file, task.id)
        update_task(task.id, attachment_path=new_path)

    cons.print(f"[green]Tache [bold]#{task.id}[/bold] creee : {title}[/green]")


# ── LIST ──────────────────────────────────────────────────────────────────────
@app.command("list")
def cli_list(
    cat:    Optional[str] = typer.Option(None, "--cat",    "-c", help="Filtrer par categorie"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="todo|in_progress|done"),
    prio:   Optional[str] = typer.Option(None, "--prio",   "-p", help="Filtrer par priorite"),
):
    """Lister les taches."""
    _ensure_db()
    cats = {c.id: c for c in get_categories()}
    cat_id = None
    if cat:
        cat_id = next(
            (c.id for c in cats.values() if c.name.lower() == cat.lower()),
            None
        )

    tasks = get_tasks(category_id=cat_id, status=status)
    if prio:
        tasks = [t for t in tasks if t.priority == prio]

    PRIO_COLOR  = {"urgent": "red", "high": "yellow", "normal": "cyan", "low": "white"}
    STATUS_ICON = {"todo": "[ ]", "in_progress": "[~]", "done": "[x]"}

    table = Table(box=box.ROUNDED, title="QuickMind - Taches", show_lines=True)
    table.add_column("ID",        style="dim",  width=4)
    table.add_column("Titre",     style="bold", width=30)
    table.add_column("Categorie",               width=12)
    table.add_column("Priorite",                width=8)
    table.add_column("Statut",                  width=14)
    table.add_column("Rappel",                  width=17)
    table.add_column("PJ",                      width=4)

    for t in tasks:
        cat_obj  = cats.get(t.category_id)
        cat_name = cat_obj.name if cat_obj else "-"
        prio_col = PRIO_COLOR.get(t.priority, "white")
        remind   = t.reminder_at.strftime("%d/%m/%Y %H:%M") if t.reminder_at else "-"
        has_att  = "[PJ]" if t.attachment_path else ""
        s_icon   = STATUS_ICON.get(t.status, "?")
        table.add_row(
            str(t.id),
            t.title,
            cat_name,
            f"[{prio_col}]{t.priority}[/{prio_col}]",
            f"{s_icon} {t.status}",
            remind,
            has_att,
        )

    cons.print(table)
    cons.print(f"[dim]{len(tasks)} tache(s) affichee(s)[/dim]")


# ── DONE ──────────────────────────────────────────────────────────────────────
@app.command("done")
def cli_done(
    task_id: int = typer.Argument(..., help="ID de la tache a terminer"),
):
    """Marquer une tache comme terminee."""
    _ensure_db()
    update_task(task_id, status="done")
    cons.print(f"[green]Tache #{task_id} marquee comme terminee.[/green]")


# ── DELETE ────────────────────────────────────────────────────────────────────
@app.command("delete")
def cli_delete(
    task_id: int = typer.Argument(..., help="ID de la tache a supprimer"),
):
    """Supprimer une tache."""
    _ensure_db()
    delete_task(task_id)
    cons.print(f"[red]Tache #{task_id} supprimee.[/red]")


# ── CAT-ADD ───────────────────────────────────────────────────────────────────
@app.command("cat-add")
def cli_cat_add(
    name:  str           = typer.Argument(..., help="Nom de la categorie"),
    color: Optional[str] = typer.Option("#1E90FF", "--color", help="Couleur hex"),
):
    """Ajouter une categorie."""
    _ensure_db()
    add_category(name, color or "#1E90FF")
    cons.print(f"[green]Categorie [bold]{name}[/bold] ajoutee.[/green]")


# ── REMINDERS ─────────────────────────────────────────────────────────────────
@app.command("reminders")
def cli_reminders():
    """Afficher les rappels en attente."""
    _ensure_db()
    tasks = get_pending_reminders()
    if not tasks:
        cons.print("[green]Aucun rappel en attente.[/green]")
        return
    for t in tasks:
        cons.print(f"[yellow]#{t.id} - {t.title} - {t.reminder_at}[/yellow]")

# ── ASK ─────────────────────────────────────────────────────────────────
@app.command("ask")
def cli_ask(
    prompt: str = typer.Argument(..., help="Question ou commande en langage naturel"),
):
    """Interroger l assistant IA local (Ollama/Mistral)."""
    from agents.local_ai import ask_ai
    cons.print(f"[dim]Envoi a Mistral...[/dim]")
    result = ask_ai(prompt)
    cons.print(f"[cyan]{result}[/cyan]")

# ── UI ────────────────────────────────────────────────────────────────────────
@app.command("ui")
def cli_ui():
    """Lancer l interface graphique."""
    import subprocess, sys
    subprocess.Popen([sys.executable, "main.py"])
    cons.print("[cyan]Interface graphique lancee.[/cyan]")


if __name__ == "__main__":
    app()
