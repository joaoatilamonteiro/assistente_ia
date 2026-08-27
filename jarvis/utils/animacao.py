"""Efeito de loading animado no terminal enquanto a IA "pensa"."""
import sys
import threading
import time


class LoadingAnimado:
    def __init__(self, mensagem="Pensando"):
        self.animacao = ['|', '/', '-', '\\']
        self.mensagem = mensagem
        self.rodando = False
        self.thread = None

    def _animar(self):
        i = 0
        while self.rodando:
            sys.stdout.write(f"\r{self.mensagem} {self.animacao[i % len(self.animacao)]} ")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1

    def iniciar(self):
        self.rodando = True
        self.thread = threading.Thread(target=self._animar)
        self.thread.start()

    def parar(self):
        self.rodando = False
        if self.thread:
            self.thread.join()
        sys.stdout.write('\r' + ' ' * (len(self.mensagem) + 5) + '\r')
        sys.stdout.flush()
