-- =====================================================================
-- Contrôle inter-tables : une facture ne peut pas précéder sa commande.
-- =====================================================================
SELECT
    i.invoice_id,
    i.order_id,
    DATE(o.order_date)   AS order_date,
    DATE(i.invoice_date) AS invoice_date,
    CAST(JULIANDAY(o.order_date) - JULIANDAY(i.invoice_date) AS INTEGER) AS jours_avance
FROM invoices i
JOIN orders o ON o.order_id = i.order_id
WHERE i.invoice_date < o.order_date;
