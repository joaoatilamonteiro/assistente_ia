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
    r"\leftrightarrow": "↔",
    r"\Leftrightarrow": "⇔",

    r"\rightarrow": "→",
    r"\Rightarrow": "⇒",
    r"\longrightarrow": "⟶",
    r"\Longrightarrow": "⟹",

    r"\leftarrow": "←",
    r"\Leftarrow": "⇐",
    r"\longleftarrow": "⟵",
    r"\Longleftarrow": "⟸",

    r"\longleftrightarrow": "⟷",
    r"\Longleftrightarrow": "⟺",

    r"\to": "→",

    r"\times": "×",
    r"\cdot": "·",
    r"\div": "÷",
    r"\pm": "±",
    r"\mp": "∓",
    r"\leq": "≤",
    r"\le": "≤",
    r"\geq": "≥",
    r"\ge": "≥",
    r"\neq": "≠",
    r"\ne": "≠",
    r"\approx": "≈",
    r"\equiv": "≡",
    r"\cong": "≅",
    r"\sim": "∼",
    r"\infty": "∞",
    r"\partial": "∂",
    r"\nabla": "∇",
    r"\sum": "∑",
    r"\prod": "∏",
    r"\oint": "∮",
    r"\int": "∫",
    r"\in": "∈",
    r"\notin": "∉",
    r"\mathbb{Z}": "ℤ",
    r"\mathbbZ": "ℤ",
    r"\mathbb{R}": "ℝ",
    r"\mathbbR": "ℝ",
    r"\implies": "⟹",
    r"\iff": "⟺",
}


_COMANDOS_MUDOS = [
    r"\left", r"\right", r"\displaystyle", r"\textstyle",
    r"\,", r"\;", r"\!", r"\:", r"\quad", r"\qquad", r"\limits"
]

# comandos de "nome de função" do LaTeX (\lim, \sin, \log...) - só tiram a barra
_FUNCOES = [
    "lim", "sin", "cos", "tan", "sec", "csc", "cot",
    "arcsin", "arccos", "arctan",
    "log", "ln", "exp",
    "max", "min", "sup", "inf", "det", "gcd", "arg", "mod",
]
# comandos que só "envolvem" o conteúdo (\text{x}, \mathcal{F}...) - mantém só o argumento
_ENVOLVENTES = ["text", "mathrm", "mathbf", "mathcal", "mathit", "boldsymbol", "operatorname"]

# placeholders pra proteger \{ e \} (chaves de conjunto, tipo \{1,2,3\}) da limpeza
# de chaves de agrupamento do latex (\frac{...}, \sqrt{...}) que roda no final
_MARCA_LBRACE = "\x00LBRACE\x00"
_MARCA_RBRACE = "\x00RBRACE\x00"

def _resolve_big_delims(expr):
    """Remove o "tamanho" de \\bigl( \\Bigr] \\biggl\\{ etc, mantendo só o delimitador."""
    return re.sub(r"\\(?:Bigg|bigg|Big|big)[lrm]?", "", expr)

def _resolve_boxed(expr):
    saida = []
    i = 0
    while i < len(expr):
        if expr[i:i + 6] == r"\boxed":
            arg, j = _pega_argumento(expr, i + 6)
            saida.append(f"⟦{_converter_expressao(arg)}⟧")
            i = j
        else:
            saida.append(expr[i])
            i += 1
    return "".join(saida)

def _resolve_brace_commands(expr, nome_comando):
    """Resolve \\underbrace{A}_{rotulo} ou \\overbrace{A}^{rotulo} -> 'A (rotulo)'."""
    token = "\\" + nome_comando
    marcador = "_" if nome_comando == "underbrace" else "^"
    saida = []
    i = 0
    while i < len(expr):
        if expr[i:i + len(token)] == token:
            arg, j = _pega_argumento(expr, i + len(token))
            k = j
            while k < len(expr) and expr[k] == " ":
                k += 1
            rotulo = ""
            if k < len(expr) and expr[k] == marcador:
                rotulo, j = _pega_argumento(expr, k + 1)
            base = _converter_expressao(arg)
            saida.append(f"{base} ({_converter_expressao(rotulo)})" if rotulo else base)
            i = j
        else:
            saida.append(expr[i])
            i += 1
    return "".join(saida)

def _resolve_envolventes(expr):
    """Resolve \\text{x}, \\mathcal{F}, \\mathbf{v}... -> mantém só o conteúdo de dentro."""
    saida = []
    i = 0
    while i < len(expr):
        casou = False
        for nome in _ENVOLVENTES:
            token = "\\" + nome
            fim_token = i + len(token)
            if expr[i:fim_token] == token and not (fim_token < len(expr) and expr[fim_token].isalpha()):
                arg, j = _pega_argumento(expr, fim_token)
                saida.append(_converter_expressao(arg))
                i = j
                casou = True
                break
        if not casou:
            saida.append(expr[i])
            i += 1
    return "".join(saida)


def _converter_expressao(expr):
    # protege \{ e \} (chaves de conjunto, ex: \{1,2,3\}) antes de qualquer coisa,
    # senão a limpeza de chaves de agrupamento no final ia apagar elas também
    expr = expr.replace(r"\{", _MARCA_LBRACE).replace(r"\}", _MARCA_RBRACE)

    expr = re.sub(r"\[\d+(?:\.\d+)?(?:pt|em|ex|cm|mm|in)\]", "", expr)
    
    for cmd in _COMANDOS_MUDOS:
        expr = expr.replace(cmd, "")
    expr = _resolve_big_delims(expr)
    for nome in _FUNCOES:
        expr = re.sub(rf"\\{nome}(?![a-zA-Z])", nome, expr)
    expr = _resolve_boxed(expr)
    expr = _resolve_brace_commands(expr, "underbrace")
    expr = _resolve_brace_commands(expr, "overbrace")
    expr = _resolve_envolventes(expr)
    expr = _resolve_frac(expr)
    expr = _resolve_sqrt(expr)
    expr = _resolve_super_sub(expr, "^", _SUPER)
    expr = _resolve_super_sub(expr, "_", _SUB)
    for cmd in sorted(_SIMBOLOS, key=len, reverse=True):
        expr = expr.replace(cmd, _SIMBOLOS[cmd])
    for cmd in sorted(_GREGO, key=len, reverse=True):
        expr = expr.replace(cmd, _GREGO[cmd])
    expr = expr.replace("{", "").replace("}", "")
    expr = expr.replace(_MARCA_LBRACE, "{").replace(_MARCA_RBRACE, "}")
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
    if texto[pos] == "{":
        fim = _casa_chave(texto, pos)
        if fim == -1:
            return texto[pos + 1:], len(texto)
        return texto[pos + 1:fim], fim + 1
    if texto[pos] == "\\":
        m = re.match(r"\\[a-zA-Z]+", texto[pos:])
        if m:
            return m.group(0), pos +len(m.group(0))
    return texto[pos], pos +1

#realiza a conversao de expressoes matematicas em geral
def _resolve_frac(expressao):
    saida = []
    i = 0
    while i < len(expressao):
        # O regex captura \frac, \dfrac ou \tfrac
        match = re.match(r"\\([dt]?frac)", expressao[i:])
        if match:
            tamanho_comando = len(match.group(0))
            arg1, j = _pega_argumento(expressao, i + tamanho_comando)
            arg2, j = _pega_argumento(expressao, j)
            saida.append(f"({_converter_expressao(arg1)}/{_converter_expressao(arg2)})")
            i = j
        else:
            saida.append(expressao[i])
            i += 1
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
def _processar_ambiente(conteudo):
    """Resolve o miolo de um \\begin{aligned}...\\end{aligned} (ou align/gather/split):
    quebra pelas linhas (\\\\), tira os '&' de alinhamento e converte cada linha."""
    linhas = conteudo.split(r"\\")
    linhas_convertidas = [
        _converter_expressao(linha.replace("&", " ")) for linha in linhas
    ]
    return "\n".join(l for l in linhas_convertidas if l)


# ==========================================
# PONTO DE ENTRADA - é essa função que o resto do projeto usa
# ==========================================
# ==========================================
# PONTO DE ENTRADA - é essa função que o resto do projeto usa
# ==========================================
_PADRAO_MATH = re.compile(
    r"\$\$(?P<dd>.+?)\$\$"
    r"|\\\[(?P<colch>.+?)\\\]"
    r"|\$(?P<dolar>.+?)\$"
    r"|\\\((?P<par>.+?)\\\)"
    r"|\\begin\{(?P<env>aligned|align\*?|gather\*?|split)\}(?P<envcont>.+?)\\end\{(?P=env)\}",
    re.DOTALL,
)


def latex_para_unicode(texto):
    """Acha os trechos de matemática em LaTeX dentro de `texto` (delimitados por
    $$..$$, \\[..\\], $..$, \\(..\\), ou um bloco \\begin{aligned}...\\end{aligned})
    e devolve o texto com esses trechos já convertidos pra unicode, sem os
    delimitadores. O resto do texto não é tocado."""
    if not texto:
        return texto

    def troca_math(m):
        conteudo_normal = next(
            (c for c in [m.group("dd"), m.group("colch"), m.group("dolar"), m.group("par")] if c is not None),
            None
        )

        if conteudo_normal is not None:
            # Protege os ambientes no meio do bloco normal antes de converter tudo
            conteudo_protegido = re.sub(
                r"\\begin\{(?P<env>aligned|align\*?|gather\*?|split)\}(?P<conteudo>.*?)\\end\{(?P=env)\}",
                lambda match: "\n" + _processar_ambiente(match.group("conteudo")) + "\n",
                conteudo_normal,
                flags=re.DOTALL
            )
            return _converter_expressao(conteudo_protegido)
        else:
            # É o match do grupo de ambiente "pelado" (sem cifrões em volta)
            env_conteudo = m.group("envcont")
            if env_conteudo:
                return "\n" + _processar_ambiente(env_conteudo) + "\n"
        return ""

    return _PADRAO_MATH.sub(troca_math, texto)