-- =====================================================================
-- KPI quotidiens par Business Unit (table alimentant le reporting)
-- Montant à risque = somme des écarts absolus des commandes en anomalie.
-- =====================================================================
SELECT
    order_date,
    COALESCE(business_unit, 'NON_RENSEIGNEE')                       AS business_unit,
    COUNT(*)                                                        AS nb_commandes,
    SUM(CASE WHEN statut = 'OK' THEN 1 ELSE 0 END)                  AS nb_ok,
    SUM(CASE WHEN statut <> 'OK' THEN 1 ELSE 0 END)                 AS nb_ko,
    ROUND(100.0 * SUM(CASE WHEN statut <> 'OK' THEN 1 ELSE 0 END)
          / COUNT(*), 3)                                            AS taux_ko_pct,
    ROUND(SUM(CASE WHEN statut <> 'OK'
                   THEN ABS(COALESCE(ecart, montant_commande)) ELSE 0 END), 2) AS montant_a_risque
FROM reconciliation
WHERE statut <> 'KO_ORPHELINE'
GROUP BY order_date, COALESCE(business_unit, 'NON_RENSEIGNEE')
ORDER BY order_date, business_unit;
