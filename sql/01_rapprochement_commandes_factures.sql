-- =====================================================================
-- Rapprochement commandes (OMS) <-> factures
-- Un statut par commande + les factures orphelines (sans commande).
-- SQL standard : s'exécute sur SQLite en local, portable sur BigQuery
-- (remplacer :tolerance par @tolerance).
-- =====================================================================
WITH factures_par_commande AS (
    SELECT
        order_id,
        COUNT(*)                 AS nb_factures,
        ROUND(SUM(amount_ttc), 2) AS montant_facture,
        MIN(invoice_id)          AS invoice_id,
        MIN(invoice_date)        AS invoice_date
    FROM invoices
    GROUP BY order_id
)
SELECT
    o.order_id,
    DATE(o.order_date)                                   AS order_date,
    o.business_unit,
    o.channel,
    o.amount_ttc                                         AS montant_commande,
    f.invoice_id,
    COALESCE(f.nb_factures, 0)                           AS nb_factures,
    f.montant_facture,
    ROUND(COALESCE(f.montant_facture, 0) - o.amount_ttc, 2) AS ecart,
    CASE
        WHEN f.order_id IS NULL                              THEN 'KO_FACTURE_MANQUANTE'
        WHEN f.nb_factures > 1                               THEN 'KO_DOUBLON'
        WHEN ABS(f.montant_facture - o.amount_ttc) > :tolerance THEN 'KO_MONTANT'
        ELSE 'OK'
    END                                                  AS statut
FROM orders o
LEFT JOIN factures_par_commande f ON f.order_id = o.order_id

UNION ALL

SELECT
    i.order_id,
    DATE(i.invoice_date),
    NULL,
    NULL,
    NULL,
    i.invoice_id,
    1,
    i.amount_ttc,
    i.amount_ttc,
    'KO_ORPHELINE'
FROM invoices i
LEFT JOIN orders o ON o.order_id = i.order_id
WHERE o.order_id IS NULL;
