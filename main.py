
if __name__ == "__main__":
    from jarvis.setup_inicial import configurar_primeira_vez
    configurar_primeira_vez()

    from interface.interface import JarvisTUI
    JarvisTUI().run()