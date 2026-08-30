import re

_SUPER = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶",
    "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ", "g": "ᵍ",
    "h": "ʰ", "i": "ⁱ", "j": "ʲ", "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ",
    "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ", "v": "ᵛ",
    "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
}

_SUB = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆",
    "7": "₇", "8": "₈", "9": "₉", "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ",
    "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ",
    "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
}

_GREGO = {
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\varepsilon": "ε", r"\epsilon": "ε", r"\zeta": "ζ", r"\eta": "η",
    r"\vartheta": "ϑ", r"\theta": "θ", r"\iota": "ι", r"\kappa": "κ",
    r"\lambda": "λ", r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ", r"\pi": "π",
    r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ", r"\upsilon": "υ",
    r"\varphi": "φ", r"\phi": "φ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Xi": "Ξ", r"\Pi": "Π", r"\Sigma": "Σ", r"\Upsilon": "Υ",
    r"\Phi": "Φ", r"\Psi": "Ψ", r"\Omega": "Ω",
}

_SIMBOLOS = {
    r"\leftrightarrow": "↔", r"\Leftrightarrow": "⇔", r"\rightarrow": "→",
    r"\Rightarrow": "⇒", r"\leftarrow": "←", r"\Leftarrow": "⇐", r"\to": "→",
    r"\times": "×", r"\cdot": "·", r"\div": "÷", r"\pm": "±", r"\mp": "∓",
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\neq": "≠", r"\ne": "≠",
    r"\approx": "≈", r"\equiv": "≡", r"\cong": "≅", r"\sim": "∼",
    r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇",
    r"\sum": "∑", r"\prod": "∏", r"\oint": "∮", r"\int": "∫",
    r"\subseteq": "⊆", r"\supseteq": "⊇", r"\subset": "⊂", r"\supset": "⊃",
    r"\cup": "∪", r"\cap": "∩", r"\emptyset": "∅", r"\forall": "∀", r"\exists": "∃",
    r"\in": "∈", r"\notin": "∉", r"\therefore": "∴", r"\because": "∵",
    r"\ldots": "…", r"\cdots": "⋯", r"\degree": "°",
}

_COMANDOS_MUDOS = [r"\left", r"\right", r"\displaystyle", r"\,", r"\;", r"\!", r"\:"]

# comandos de "nome de função" do LaTeX (\lim, \sin, \log...) - só tiram a barra
_FUNCOES = [
    "lim", "sin", "cos", "tan", "sec", "csc", "cot", "log", "ln", "exp",
    "max", "min", "sup", "inf", "det", "gcd", "arg", "mod",
]


def _converter_expressao(expr):
    for cmd in _COMANDOS_MUDOS:
        expr = expr.replace(cmd, "")
    for nome in _FUNCOES:
        expr = re.sub(rf"\\{nome}(?![a-zA-Z])", nome, expr)
    expr = _resolve_frac(expr)
    expr = _resolve_sqrt(expr)
    expr = _resolve_super_sub(expr, "^", _SUPER)
    expr = _resolve_super_sub(expr, "_", _SUB)
    for cmd in sorted(_SIMBOLOS, key=len, reverse=True):
        expr = expr.replace(cmd, _SIMBOLOS[cmd])
    for cmd in sorted(_GREGO, key=len, reverse=True):
        expr = expr.replace(cmd, _GREGO[cmd])
    expr = expr.replace("{", "").replace("}", "")
    expr = re.sub(r"[ \t]+", " ", expr).strip()
    return expr

#para saber aonde fecha e aonde começa baseado nas chaves
def _casa_chave(texto,inicio):
    nivel = 0
    for i in range(inicio, len(texto)):
        if texto[i] == "{":
            nivel +=1
        elif texto[i] == "}":
            nivel -= 1
            if nivel == 0:
                return i
    return -1

#pega o proximo argumento de um latex a partir de pos
def _pega_argumento(texto, pos):
    while pos < len(texto) and texto[pos] == " ":
        pos +=1
    if pos >= len(texto):
        return "",pos
    if texto[pos] == "\\":
        m = re.match(r"\\[a-zA-Z]+", texto[pos:])
        if m:
            return m.group(0), pos +len(m.group(0))
    return texto[pos], pos +1

#realiza a conversao de expressoes matematicas em geral
def _resolve_frac(expressao):
    saida = []
    i = 0
    while i<len(expressao):
        if expressao[i:i+5] == r"\frac":
            arg1, j = _pega_argumento(expressao, i+5)
            arg2, j = _pega_argumento(expressao, j)
            saida.append(f"({_converter_expressao(arg1)}/{_converter_expressao(arg2)})")
            i = j
        else:
            saida.append(expressao[i])
            i+=1
    return "".join(saida)


def _resolve_sqrt(expr):
    saida = []
    i = 0
    while i < len(expr):
        if expr[i:i + 5] == r"\sqrt":
            j = i + 5
            indice_unicode = ""
            if j < len(expr) and expr[j] == "[":
                fim_indice = expr.find("]", j)
                if fim_indice != -1:
                    indice_unicode = "".join(_SUPER.get(c, c) for c in expr[j + 1:fim_indice])
                    j = fim_indice + 1
            arg, j = _pega_argumento(expr, j)
            saida.append(f"{indice_unicode}√({_converter_expressao(arg)})")
            i = j
        else:
            saida.append(expr[i])
            i += 1
    return "".join(saida)


def _resolve_super_sub(expr, simbolo, mapa):
    saida = []
    i = 0
    while i < len(expr):
        if expr[i] == simbolo:
            arg, j = _pega_argumento(expr, i + 1)
            arg_conv = _converter_expressao(arg) if ("\\" in arg) else arg
            convertido = "".join(mapa.get(c, c) for c in arg_conv)
            # se sobrar algum caractere sem correspondente unicode, cai pro formato "^(...)"
            if any((c not in mapa) and c.strip() for c in arg_conv):
                convertido = f"({arg_conv})"
                convertido = ("^" if simbolo == "^" else "_") + convertido
            saida.append(convertido)
            i = j
        else:
            saida.append(expr[i])
            i += 1
    return "".join(saida)





# ==========================================
# PONTO DE ENTRADA - é essa função que o resto do projeto usa
# ==========================================
_PADRAO_MATH = re.compile(
    r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\$(.+?)\$|\\\((.+?)\\\)",
    re.DOTALL,
)


def latex_para_unicode(texto):
    """Acha os trechos de matemática em LaTeX dentro de `texto` (delimitados por
    $$..$$, \\[..\\], $..$ ou \\(..\\)) e devolve o texto com esses trechos já
    convertidos pra unicode, sem os delimitadores. O resto do texto não é tocado."""
    if not texto:
        return texto

    def _troca(m):
        conteudo = next(g for g in m.groups() if g is not None)
        return _converter_expressao(conteudo)

    return _PADRAO_MATH.sub(_troca, texto)