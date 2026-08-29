
# O novo cardápio que aceita listas
ferramentas_jarvis = [
    {
        "type": "function",
        "function": {
            "name": "adicionar_multiplos_eventos",
            "description": "Adiciona um ou VÁRIOS eventos na agenda do Google do usuário de uma só vez.",
            "parameters": {
                "type": "object",
                "properties": {
                    "eventos": {
                        "type": "array",
                        "description": "Uma lista contendo todos os eventos que precisam ser agendados.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "resumo": {
                                    "type": "string",
                                    "description": "O título do evento (ex: 'Prova de Matemática')"
                                },
                                "data_hora_inicio": {
                                    "type": "string",
                                    "description": "Data e hora de início no formato ISO 8601 (ex: '2026-08-17T15:00:00-03:00')"
                                },
                                "data_hora_fim": {
                                    "type": "string",
                                    "description": "Data e hora de término no formato ISO 8601"
                                },
                                "lembrete_minutos": {
                                    "type": "integer",
                                    "description": "Tempo de antecedência do lembrete em minutos. (ex: 5 dias = 7200)."
                                }
                            },
                            "required": ["resumo", "data_hora_inicio", "data_hora_fim"]
                        }
                    }
                },
                "required": ["eventos"]
            }
        },
    },
    {
            "type": "function",
            "function": {
                "name": "apagar_eventos_por_termo",
                "description": "Busca e apaga eventos futuros do calendário com base em uma palavra-chave ou título.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "termo_busca": {
                            "type": "string",
                            "description": "Parte do título ou nome exato do evento a ser apagado (ex: 'Algebra Linear')."
                        }
                    },
                    "required": ["termo_busca"]
                }
            }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_proximos_eventos",
            "description": "Lista os próximos eventos futuros da agenda do Google do usuário. Use quando o usuário perguntar 'quando é', 'o que tenho marcado', 'quais eventos', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo_busca": {
                        "type": "string",
                        "description": "Palavra-chave pra filtrar os eventos (ex: 'prova'). Deixe vazio pra listar todos os próximos eventos."
                    },
                    "dias_a_frente": {
                        "type": "integer",
                        "description": "Quantos dias pra frente buscar. Padrão 90 se não especificado."
                    }
                },
                "required": []
            }
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editar_evento_por_termo",
            "description": "Busca um evento futuro no calendário por uma palavra-chave e edita o seu título e/ou horários.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo_busca": {
                        "type": "string",
                        "description": "Parte do título ou nome exato do evento a ser editado (ex: 'Teste de MP')."
                    },
                    "novo_resumo": {
                        "type": "string",
                        "description": "Novo título para o evento, caso o usuário queira mudar. Deixe vazio se não for mudar."
                    },
                    "nova_data_hora_inicio": {
                        "type": "string",
                        "description": "Nova data e hora de início no formato ISO 8601. Deixe vazio se não for mudar."
                    },
                    "nova_data_hora_fim": {
                        "type": "string",
                        "description": "Nova data e hora de término no formato ISO 8601. Deixe vazio se não for mudar."
                    },
                    "novo_lembrete_minutos":{
                        "type": "integer",
                        "description": "Novo tempo de antecedência do lembrete em minutos (ex: 5 dias = 7200). Deixe vazio se não for mudar o lembrete atual."
                    }

                },
                "required": ["termo_busca"]  # A IA só é obrigada a passar o termo de busca!
            }
        }
    }

]
