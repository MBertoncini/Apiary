-- ============================================================================
-- REPORT READ-ONLY: pagamenti "fantasma" da attrezzature (bilancio gonfiato)
-- ============================================================================
--
-- Solo SELECT: non modifica nulla. Serve a fotografare, PRIMA di lanciare
--   python manage.py pulisci_pagamenti_attrezzature [--user X] --apply
-- quanti/quali Pagamento orfani gonfiano ancora le "uscite" del Bilancio
-- Economico.
--
-- Criterio "orfano automatico" — identico a quello del management command
-- (core/management/commands/pulisci_pagamenti_attrezzature.py, PREFISSI_AUTO):
--   * spesa_attrezzatura_id IS NULL   -> non collegato a nessuna spesa
--   * destinatario_id       IS NULL   -> pagamento personale (entra nel bilancio)
--   * descrizione LIKE uno dei prefissi generati dal client vecchio (<= build 19)
--
-- Il Bilancio Economico conta come "uscite":
--   SpesaAttrezzatura + Pagamento(destinatario IS NULL AND spesa_attrezzatura IS NULL)
-- (vedi statistiche/views/widgets.py:437-441). Questi orfani ricadono nel
-- secondo addendo: eliminarli/ricollegarli li toglie dal bilancio.
--
-- DBMS di produzione: MySQL. Per una copia sqlite locale vedi le note in fondo.
-- Per limitare a un utente: togli il commento a  AND au.username = @username
-- (e imposta @username qui sotto).
-- ============================================================================

SET @username := NULL;   -- es.  SET @username := 'michele';  (NULL = tutti)

-- ----------------------------------------------------------------------------
-- 0) Vista di appoggio riusabile: l'insieme degli orfani automatici.
--    (Definita come subquery ripetuta più sotto; MySQL non ha CTE persistenti
--     tra statement, quindi la condizione è ripetuta in ogni query.)
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- 1) TOTALE COMPLESSIVO  (il numero che ti aspetti ~200 €)
-- ----------------------------------------------------------------------------
SELECT
    COUNT(*)                         AS n_pagamenti,
    COALESCE(SUM(p.importo), 0)      AS totale_euro,
    MIN(p.data)                      AS dal,
    MAX(p.data)                      AS al
FROM core_pagamento p
JOIN auth_user au ON au.id = p.utente_id
WHERE p.spesa_attrezzatura_id IS NULL
  AND p.destinatario_id      IS NULL
  AND (
        p.descrizione LIKE 'Acquisto attrezzatura:%'
     OR p.descrizione LIKE 'Manutenzione attrezzatura:%'
     OR p.descrizione LIKE 'Spesa attrezzatura (%'
      )
  AND (@username IS NULL OR au.username = @username);

-- ----------------------------------------------------------------------------
-- 2) RIPARTIZIONE PER UTENTE
-- ----------------------------------------------------------------------------
SELECT
    au.username,
    COUNT(*)                    AS n_pagamenti,
    COALESCE(SUM(p.importo), 0) AS totale_euro
FROM core_pagamento p
JOIN auth_user au ON au.id = p.utente_id
WHERE p.spesa_attrezzatura_id IS NULL
  AND p.destinatario_id      IS NULL
  AND (
        p.descrizione LIKE 'Acquisto attrezzatura:%'
     OR p.descrizione LIKE 'Manutenzione attrezzatura:%'
     OR p.descrizione LIKE 'Spesa attrezzatura (%'
      )
  AND (@username IS NULL OR au.username = @username)
GROUP BY au.username
ORDER BY totale_euro DESC;

-- ----------------------------------------------------------------------------
-- 3) RIPARTIZIONE PER ANNO (il bilancio è per anno: così sai in che anno cade)
-- ----------------------------------------------------------------------------
SELECT
    YEAR(p.data)                AS anno,
    COUNT(*)                    AS n_pagamenti,
    COALESCE(SUM(p.importo), 0) AS totale_euro
FROM core_pagamento p
JOIN auth_user au ON au.id = p.utente_id
WHERE p.spesa_attrezzatura_id IS NULL
  AND p.destinatario_id      IS NULL
  AND (
        p.descrizione LIKE 'Acquisto attrezzatura:%'
     OR p.descrizione LIKE 'Manutenzione attrezzatura:%'
     OR p.descrizione LIKE 'Spesa attrezzatura (%'
      )
  AND (@username IS NULL OR au.username = @username)
GROUP BY YEAR(p.data)
ORDER BY anno;

-- ----------------------------------------------------------------------------
-- 4) ELENCO DETTAGLIATO  (uno per riga: da confrontare con l'app)
-- ----------------------------------------------------------------------------
SELECT
    p.id,
    au.username,
    p.data,
    p.importo,
    p.descrizione,
    p.gruppo_id
FROM core_pagamento p
JOIN auth_user au ON au.id = p.utente_id
WHERE p.spesa_attrezzatura_id IS NULL
  AND p.destinatario_id      IS NULL
  AND (
        p.descrizione LIKE 'Acquisto attrezzatura:%'
     OR p.descrizione LIKE 'Manutenzione attrezzatura:%'
     OR p.descrizione LIKE 'Spesa attrezzatura (%'
      )
  AND (@username IS NULL OR au.username = @username)
ORDER BY au.username, p.data, p.id;

-- ----------------------------------------------------------------------------
-- 5) SICUREZZA: quali orfani il command RICOLLEGHEREBBE (step B) vs.
--    quali CANCELLEREBBE davvero (step C).
--
--    Un orfano è "ricollegabile" se esiste ancora una SpesaAttrezzatura
--    con stesso pagante+importo+data (o, per le spese di gruppo, stesso
--    gruppo+importo+data). Quelli senza corrispondenza sono i veri fantasmi
--    da spesa inesistente. Utile per capire cosa succederà con --apply.
-- ----------------------------------------------------------------------------
SELECT
    p.id,
    au.username,
    p.data,
    p.importo,
    p.descrizione,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM core_spesaattrezzatura s
            WHERE s.importo = p.importo
              AND s.data    = p.data
              AND (s.pagato_da_id = p.utente_id OR s.utente_id = p.utente_id)
        ) THEN 'RICOLLEGABILE (step B: match su pagante)'
        WHEN p.gruppo_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM core_spesaattrezzatura s
            WHERE s.importo   = p.importo
              AND s.data      = p.data
              AND s.gruppo_id = p.gruppo_id
        ) THEN 'RICOLLEGABILE (step B: match su gruppo)'
        ELSE 'FANTASMA -> verra'' ELIMINATO (step C)'
    END AS esito_atteso
FROM core_pagamento p
JOIN auth_user au ON au.id = p.utente_id
WHERE p.spesa_attrezzatura_id IS NULL
  AND p.destinatario_id      IS NULL
  AND (
        p.descrizione LIKE 'Acquisto attrezzatura:%'
     OR p.descrizione LIKE 'Manutenzione attrezzatura:%'
     OR p.descrizione LIKE 'Spesa attrezzatura (%'
      )
  AND (@username IS NULL OR au.username = @username)
ORDER BY esito_atteso, au.username, p.data;

-- ----------------------------------------------------------------------------
-- 6) CONTROPROVA: totale "uscite" che il Bilancio vede per un anno, spezzato
--    tra spese reali e pagamenti (di cui gli orfani sono un sottoinsieme).
--    Cambia @anno per l'anno che vedi gonfiato nell'app.
-- ----------------------------------------------------------------------------
SET @anno := YEAR(CURDATE());   -- es. SET @anno := 2026;

SELECT 'SpesaAttrezzatura (uscite reali)' AS voce,
       COALESCE(SUM(s.importo), 0)        AS totale_euro
FROM core_spesaattrezzatura s
JOIN auth_user au ON au.id = s.utente_id
WHERE YEAR(s.data) = @anno
  AND (@username IS NULL OR au.username = @username)
UNION ALL
SELECT 'Pagamenti personali NON collegati a spesa (include i fantasma)' AS voce,
       COALESCE(SUM(p.importo), 0)        AS totale_euro
FROM core_pagamento p
JOIN auth_user au ON au.id = p.utente_id
WHERE p.destinatario_id       IS NULL
  AND p.spesa_attrezzatura_id IS NULL
  AND YEAR(p.data) = @anno
  AND (@username IS NULL OR au.username = @username);

-- ============================================================================
-- NOTE per copia sqlite locale (DEBUG=True, db.sqlite3):
--   * YEAR(p.data)      ->  CAST(strftime('%Y', p.data) AS INTEGER)
--   * YEAR(CURDATE())   ->  CAST(strftime('%Y','now')   AS INTEGER)
--   * SET @var := ...   ->  sqlite non ha variabili di sessione: sostituisci
--                           a mano @username con 'tuo_username' (o rimuovi la
--                           condizione) e @anno con l'anno.
-- ============================================================================
