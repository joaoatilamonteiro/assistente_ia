import time


def formatar_duracao(segundos):
    if segundos < 60:
        return f"{segundos:.2f}s"
    minutos = int(segundos // 60)
    resto = segundos % 60
    return f"{minutos}min {resto:.1f}s"
