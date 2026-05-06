"""QuickMind — Point d entree principal."""
import sys
import traceback


def main():
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
