"""
QuickMind — Point d entree principal.
Fix DPI : scaling CTk applique AVANT creation des widgets = fluide.
"""
import sys
import ctypes
import traceback


def _set_dpi_awareness():
    """Force Per-Monitor V2 DPI awareness."""
    try:
        result = ctypes.windll.shcore.SetProcessDpiAwareness(2)
        if result == 0:
            print("[DPI] Per-Monitor V2 active.")
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            print("[DPI] System DPI active (fallback).")
        except Exception:
            pass


def _get_primary_dpi() -> float:
    """
    Recupere le DPI de l ecran principal AVANT de creer la fenetre.
    Utilise GetDpiForSystem() — disponible sans handle de fenetre.
    """
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        factor = dpi / 96.0
        print(f"[DPI] Ecran principal : DPI={dpi} factor={factor:.2f}")
        return round(factor, 2)
    except Exception as e:
        print(f"[DPI] Fallback 1.0 : {e}")
        return 1.0


def _apply_ctk_scaling(font_scale: float = 1.2):
    """
    Applique le scaling CustomTkinter AVANT toute creation de fenetre.
    C est la cle : CTk lit ces valeurs a l initialisation des widgets.
    Resultat : polices et widgets au bon taille DES LE DEBUT, sans redraw.
    """
    import customtkinter as ctk
    dpi_factor = _get_primary_dpi()
    widget_scaling = round(dpi_factor * font_scale, 2)
    window_scaling = round(dpi_factor, 2)

    ctk.set_widget_scaling(widget_scaling)
    ctk.set_window_scaling(window_scaling)
    print(f"[DPI] CTk scaling : widget={widget_scaling} "
          f"window={window_scaling} "
          f"(dpi={dpi_factor} x font={font_scale})")


def main():
    # 1. DPI awareness Windows EN PREMIER
    _set_dpi_awareness()

    # 2. Lire font_scale depuis config
    try:
        import yaml
        from pathlib import Path
        cfg_path = Path(__file__).parent / "config.yaml"
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        font_scale = cfg.get("app", {}).get("font_scale", 1.2)
    except Exception:
        font_scale = 1.2

    # 3. Appliquer le scaling CTk AVANT toute fenetre
    _apply_ctk_scaling(font_scale=font_scale)

    # 4. Lancer l app (widgets crees avec le bon scaling d emblee)
    try:
        from ui.app_window import App
        app = App()
        app.mainloop()
    except Exception as e:
        print("\n" + "="*60)
        print("ERREUR AU DEMARRAGE DE QUICKMIND :")
        print("="*60)
        traceback.print_exc()
        print("="*60)
        print("\nAppuie sur Entree pour fermer...")
        input()
        sys.exit(1)


if __name__ == "__main__":
    main()
