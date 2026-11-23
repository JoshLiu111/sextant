-- My Portfolio (P4): FIFO lots and booked realized P&L (docs/adr/0004).
--
-- portfolio_holdings.lots: the holding's open lots, oldest first, as
-- [{"quantity": number, "cost_price": number}] (cost per unit including buy fees).
-- NULL means one lot of the whole holding at its cost_price: holdings entered
-- or edited by hand, and holdings saved before this migration.
--
-- portfolio_transactions.realized_pnl: for a sell, the P&L booked when it was
-- imported (proceeds less fees less the FIFO cost of the lots it closed), in the
-- row's currency. NULL for buys.

ALTER TABLE portfolio_holdings ADD COLUMN lots jsonb CHECK (lots IS NULL OR jsonb_typeof(lots) = 'array');

ALTER TABLE portfolio_transactions ADD COLUMN realized_pnl numeric CHECK (side = 'sell' OR realized_pnl IS NULL);
