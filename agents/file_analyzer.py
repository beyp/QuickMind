"""
Analyseur de fichiers via IA locale (Mistral/Ollama).
Supporte : PDF, Word, Excel, TXT, Markdown, Images, EML, MSG
"""
import os
import re
from pathlib import Path


# ── Extracteurs de texte ──────────────────────────────────────────────────────

def _extract_pdf(path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(path)
    pages  = []
    for page in reader.pages[:10]:  # max 10 pages
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)


def _extract_docx(path: str) -> str:
    from docx import Document
    doc   = Document(path)
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(lines)


def _extract_xlsx(path: str) -> str:
    import openpyxl
    wb    = openpyxl.load_workbook(path, read_only=True, data_only=True)
    lines = []
    for sheet in wb.worksheets[:3]:  # max 3 feuilles
        lines.append(f"=== Feuille : {sheet.title} ===")
        for row in sheet.iter_rows(max_row=50, values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                lines.append("  |  ".join(cells))
    return "\n".join(lines)


def _extract_txt(path: str) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    return ""


def _extract_eml(path: str) -> str:
    import email
    with open(path, "rb") as f:
        msg = email.message_from_bytes(f.read())
    subject = msg.get("Subject", "")
    sender  = msg.get("From", "")
    body    = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                break
    else:
        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
    return f"De : {sender}\nObjet : {subject}\n\n{body}"


def _extract_msg(path: str) -> str:
    try:
        import extract_msg
        msg = extract_msg.Message(path)
        return (
            f"De : {msg.sender}\n"
            f"Objet : {msg.subject}\n\n"
            f"{msg.body or ''}"
        )
    except ImportError:
        return f"[Fichier .msg — installez extract-msg : pip install extract-msg]"
    except Exception as e:
        return f"[Erreur lecture .msg : {e}]"


def _extract_image(path: str) -> str:
    """
    Pour les images, on encode en base64 et on utilise
    Mistral vision si disponible, sinon message informatif.
    """
    import base64
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"[IMAGE_B64:{b64[:100]}...]"   # marqueur special


def extract_text(path: str) -> tuple[str, str]:
    """
    Extrait le texte d un fichier.
    Retourne (texte_extrait, type_fichier).
    """
    ext = Path(path).suffix.lower()
    extractors = {
        ".pdf":  ("PDF",        _extract_pdf),
        ".docx": ("Word",       _extract_docx),
        ".doc":  ("Word",       _extract_docx),
        ".xlsx": ("Excel",      _extract_xlsx),
        ".xls":  ("Excel",      _extract_xlsx),
        ".txt":  ("Texte",      _extract_txt),
        ".md":   ("Markdown",   _extract_txt),
        ".csv":  ("CSV",        _extract_txt),
        ".eml":  ("Email",      _extract_eml),
        ".msg":  ("Email Outlook", _extract_msg),
        ".png":  ("Image",      _extract_image),
        ".jpg":  ("Image",      _extract_image),
        ".jpeg": ("Image",      _extract_image),
        ".gif":  ("Image",      _extract_image),
        ".bmp":  ("Image",      _extract_image),
        ".webp": ("Image",      _extract_image),
    }
    if ext not in extractors:
        return f"[Type de fichier non supporte : {ext}]", "Inconnu"
    file_type, fn = extractors[ext]
    try:
        text = fn(path)
        return text or "[Fichier vide ou illisible]", file_type
    except Exception as e:
        return f"[Erreur extraction : {e}]", file_type


# ── Analyse IA via Mistral ────────────────────────────────────────────────────

ANALYSIS_PROMPT = """Tu es un assistant de gestion de taches.
Analyse ce document et reponds UNIQUEMENT en JSON valide.

Format obligatoire :
{
  "title": "titre court de la tache (max 80 caracteres)",
  "description": "resume du document en 2-4 phrases, actions cles identifiees",
  "priority": "low|normal|high|urgent",
  "category": "une parmi : Travail|Perso|Projets|IA / Dev",
  "actions": ["action 1", "action 2", "action 3"],
  "summary": "resume en 1 phrase du contenu du document"
}

Regles :
- title : accrocheur et actionnable
- priority : urgent si echeance proche ou critique, high si important
- actions : liste des choses a faire identifiees dans le document (max 5)
- Reponds en francais
"""


def analyze_with_ai(path: str, categories: list[str] = None) -> dict:
    """
    Analyse un fichier avec Mistral et retourne un dict de suggestions.
    """
    import json
    import ollama

    text, file_type = extract_text(path)
    fname = Path(path).name

    # Limiter le texte envoye a Mistral
    text_truncated = text[:4000] if len(text) > 4000 else text

    is_image = text.startswith("[IMAGE_B64:")

    if is_image:
        # Extraire le base64 complet pour vision
        import base64
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        user_content = [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text",
             "text": ANALYSIS_PROMPT + f"\n\nFichier : {fname} (Image)"}
        ]
        try:
            response = ollama.chat(
                model="llava",   # modele vision
                messages=[{"role": "user", "content": user_content}],
                options={"temperature": 0.1}
            )
        except Exception:
            # Fallback si llava pas disponible
            return {
                "title": f"Analyser image : {fname}",
                "description": f"Image recue : {fname}. Analyse manuelle requise.",
                "priority": "normal",
                "category": categories[0] if categories else "Travail",
                "actions": [f"Examiner l image {fname}"],
                "summary": f"Image : {fname}",
                "file_type": "Image",
                "file_name": fname,
            }
    else:
        cat_hint = f"Categories disponibles : {', '.join(categories)}" if categories else ""
        prompt   = (
            ANALYSIS_PROMPT +
            f"\n{cat_hint}\n\n"
            f"Fichier : {fname} (type : {file_type})\n\n"
            f"Contenu :\n{text_truncated}"
        )
        try:
            response = ollama.chat(
                model="mistral",
                messages=[
                    {"role": "system",
                     "content": "Tu analyses des documents et retournes du JSON."},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.1}
            )
        except Exception as e:
            err = str(e)
            if "connection" in err.lower() or "refused" in err.lower():
                raise RuntimeError("Ollama n est pas demarre. Lance : ollama serve")
            raise

    raw = response["message"]["content"].strip()

    # Extraire le JSON
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
        except Exception:
            result = {}
    else:
        result = {}

    # Valeurs par defaut si manquantes
    result.setdefault("title",       f"Tache depuis : {fname}")
    result.setdefault("description", text_truncated[:300])
    result.setdefault("priority",    "normal")
    result.setdefault("category",    categories[0] if categories else "Travail")
    result.setdefault("actions",     [])
    result.setdefault("summary",     "")
    result["file_type"] = file_type
    result["file_name"] = fname

    return result
