-- ============================================================================
-- REPORT READ-ONLY mirato all'utente (username che inizia per 'leob').
-- Solo SELECT. Serve a capire da dove arrivano i ~200 € di "uscite" nel
-- Bilancio Economico, dato che NON risultano pagamenti fantasma da attrezzatura.
--
-- Il bilancio somma, per l'utente loggato e per anno:
--    SpesaAttrezzatura(utente)               [= ciò che legge "analisi spese"]
--  + Pagamento(utente, destinatario IS NULL, spesa_attrezzatura IS NULL)
-- (statistiche/views/widgets.py:430-448)
-- ============================================================================

-- 0) Chi sono gli utenti che matchano (verifica lo spelling esatto).
SELECT id, username, email, is_active
FROM auth_user
WHERE username LIKE 'leob%';

-- 1) SPESE ATTREZZATURA dell'utente — elenco completo.
--    È esattamente ciò che "Statistiche > Analisi > Spese" mostra.
--    Se qui c'è roba ma nell'app l'analisi è vuota, il problema è nella vista
--    analisi (filtro anno/entità), non nei dati.
SELECT s.id, au.username, s.data, s.importo, s.tipo, s.descrizione,
       s.attrezzatura_id, s.gruppo_id
FROM core_spesaattrezzatura s
JOIN auth_user au ON au.id = s.utente_id
WHERE au.username LIKE 'leob%'
ORDER BY s.data DESC;

-- 2) SPESE ATTREZZATURA — totale per anno (il numero che entra nel bilancio).
SELECT YEAR(s.data) AS anno, COUNT(*) AS n, COALESCE(SUM(s.importo),0) AS totale_euro
FROM core_spesaattrezzatura s
JOIN auth_user au ON au.id = s.utente_id
WHERE au.username LIKE 'leob%'
GROUP BY YEAR(s.data)
ORDER BY anno;

-- 3) ATTREZZATURE ancora esistenti dell'utente, con prezzo di acquisto.
--    Se hai cancellato le ARNIE ma NON le attrezzature collegate, queste sono
--    rimaste: la loro spesa di acquisto continua a pesare sul bilancio.
SELECT a.id, au.username, a.nome, a.data_acquisto, a.prezzo_acquisto, a.stato
FROM core_attrezzatura a
JOIN auth_user au ON au.id = a.proprietario_id
WHERE au.username LIKE 'leob%'
ORDER BY a.id DESC;

-- 4) TUTTI i pagamenti dell'utente (personali e no) — per completezza.
SELECT p.id, au.username, p.data, p.importo, p.descrizione,
       p.destinatario_id, p.spesa_attrezzatura_id, p.gruppo_id
FROM core_pagamento p
JOIN auth_user au ON au.id = p.utente_id
WHERE au.username LIKE 'leob%'
ORDER BY p.data DESC;

-- 5) RIPRODUZIONE ESATTA delle "uscite" del bilancio, per anno.
--    Deve tornare col numero che vedi nell'app (~200 €).
SELECT anno,
       SUM(spese_attrezzatura) AS spese_attrezzatura,
       SUM(pagamenti_personali) AS pagamenti_personali,
       SUM(spese_attrezzatura) + SUM(pagamenti_personali) AS uscite_totali
FROM (
    SELECT YEAR(s.data) AS anno,
           SUM(s.importo) AS spese_attrezzatura,
           0              AS pagamenti_personali
    FROM core_spesaattrezzatura s
    JOIN auth_user au ON au.id = s.utente_id
    WHERE au.username LIKE 'leob%'
    GROUP BY YEAR(s.data)
    UNION ALL
    SELECT YEAR(p.data) AS anno,
           0              AS spese_attrezzatura,
           SUM(p.importo) AS pagamenti_personali
    FROM core_pagamento p
    JOIN auth_user au ON au.id = p.utente_id
    WHERE au.username LIKE 'leob%'
      AND p.destinatario_id       IS NULL
      AND p.spesa_attrezzatura_id IS NULL
    GROUP BY YEAR(p.data)
) x
GROUP BY anno
ORDER BY anno;
