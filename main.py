"""
QuickMind — Point d entree principal.
Fix DPI : Per-Monitor V2 pour eviter les lags multi-ecrans.
"""
import sys
import ctypes
import traceback


def _set_dpi_awareness():
    """
    Force le mode DPI Per-Monitor V2 sur Windows.
    DOIT etre appele AVANT toute initialisation de fenetre Tkinter.
    Evite les problemes de redraw lors du passage entre ecrans
    avec des DPI/scaling differents.
    """
    try:
        # Per Monitor DPI Aware V2 (Windows 10 1703+)
        result = ctypes.windll.shcore.SetProcessDpiAwareness(2)
        if result == 0:
            print("[DPI] Mode Per-Monitor V2 active.")
        else:
            raise Exception(f"Code retour : {result}")
    except Exception:
        try:
            # Fallback : System DPI Aware
            ctypes.windll.user32.SetProcessDPIAware()
            print("[DPI] Mode System DPI Aware active (fallback).")
        except Exception as e:
            print(f"[DPI] Impossible : {e}")


def main():
    # Fix DPI EN PREMIER — avant toute fenetre
    _set_dpi_awareness()

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
