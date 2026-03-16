import re

# Tabelle accessibili all'AI (whitelist — solo tabelle sicure, no auth sensibili)
ALLOWED_TABLES = {
    'core_apiario', 'core_arnia', 'core_controlloarnia',
    'core_regina', 'core_storiaregine',
    'core_smielatura', 'core_melario',
    'core_vendita', 'core_dettagliovendita',
    'core_fioritura', 'core_fiorituraconferma',
    'core_attrezzatura', 'core_categoriaartrezzatura',
    'core_spesaattrezzatura', 'core_inventarioattrezzature',
    'core_trattamentosanitario', 'core_tipotrattamento',
    'core_pagamento', 'core_quotautente',
    'core_gruppo', 'core_membrogruppo',
    'core_nucleo', 'core_controlloarnia',
}

# Keyword pericolose da bloccare sempre
FORBIDDEN_KEYWORDS = [
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
    'TRUNCATE', 'EXEC', 'EXECUTE', 'UNION', '--', ';--',
    'AUTH_USER', 'AUTHTOKEN', 'DJANGO_SESSION', 'DJANGO_ADMIN',
    'AUTH_PASSWORD', 'PASSWORD', 'TOKEN', 'SECRET',
    'XP_', 'SP_', 'INFORMATION_SCHEMA', 'PERFORMANCE_SCHEMA',
    'SLEEP(', 'BENCHMARK(', 'LOAD_FILE', 'INTO OUTFILE', 'INTO DUMPFILE',
]


def validate_sql(sql: str) -> tuple:
    """
    Valida e sanitizza una query SQL generata dall'AI.
    Ritorna (True, sql_sanitizzato) oppure (False, messaggio_errore).
    """
    sql_stripped = sql.strip()
    sql_upper = sql_stripped.upper()

    # Deve iniziare con SELECT
    if not sql_upper.startswith('SELECT'):
        return False, 'La query deve iniziare con SELECT'

    # Verifica keyword vietate
    for kw in FORBIDDEN_KEYWORDS:
        if kw in sql_upper:
            return False, f'Operazione non permessa: {kw}'

    # Rimuovi punto e virgola finale multiplo
    sql_clean = sql_stripped.rstrip(';').strip()

    # Aggiungi LIMIT se mancante
    if 'LIMIT' not in sql_upper:
        sql_clean = sql_clean + ' LIMIT 500'

    return True, sql_clean
