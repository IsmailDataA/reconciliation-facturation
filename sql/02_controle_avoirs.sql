-- =====================================================================
-- Contrôle des avoirs : un statut par avoir, rattaché à l'opérateur
-- qui l'a saisi (base des notifications automatiques).
-- =====================================================================
WITH ref_factures AS (
    SELECT invoice_id, MAX(amount_ttc) AS amount_ttc, MIN(invoice_date) AS invoice_date
    FROM invoices
    GROUP BY invoice_id
)
SELECT
    c.credit_id,
    c.operator,
    c.invoice_id,
    DATE(c.created_at)  AS created_at,
    c.amount,
    c.reason_code,
    f.amount_ttc        AS montant_facture,
    CASE
        WHEN f.invoice_id IS NULL                       THEN 'KO_AVOIR_ORPHELIN'
        WHEN c.reason_code IS NULL OR c.reason_code = '' THEN 'KO_MOTIF_MANQUANT'
        WHEN c.amount > f.amount_ttc                    THEN 'KO_AVOIR_SUPERIEUR_FACTURE'
        ELSE 'OK'
    END                 AS statut
FROM credit_notes c
LEFT JOIN ref_factures f ON f.invoice_id = c.invoice_id;
