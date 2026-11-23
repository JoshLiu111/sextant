# Realized P&L: FIFO lots kept on each holding, booked when a sell is imported

**Status:** accepted (ticket #29).

A saved portfolio's holdings are the source of truth for what is held now, and the user can edit them by hand at any time (`PUT /portfolios/{id}`). Imported transactions (#28) are the history an import applied on top of whatever was held then. So the stored transactions alone do not explain the holdings: shares entered by hand have no buy row, and a hand edit can change a quantity or cost that earlier imports produced.

We decided:

- **Lot method: FIFO.** Each holding keeps its open lots, oldest first (`portfolio_holdings.lots`, NULL = one lot of the whole holding). A buy adds a lot at `price + fees / quantity`. A sell closes the oldest lots first. A holding's cost price is the average cost of its open lots, so unrealized P&L (`quantity x (price - cost price)`) and realized P&L always use the same lots, and realized + unrealized equals the cash result of the trades.
- **Realized P&L is booked when a sell is imported**: `quantity x price - fees - FIFO cost of the closed lots`, stored on the sell row (`portfolio_transactions.realized_pnl`, in the row's currency). A position's realized P&L is the sum of its booked sells; it is never recomputed by replaying transactions.
- **Hand-entered shares are the oldest lot.** A holding entered by hand is one lot at the entered cost. A later imported sell closes it first, so selling shares that have no buy row still books a P&L.
- **Drift from hand edits.** A holding sent back unchanged in a `PUT` (same ticker, quantity, cost price and currency, as when renaming) keeps its lots. A holding whose quantity, cost or currency changed starts again as one lot at the entered cost. Hand edits never change P&L already booked: a realized gain stays realized.

## Considered options

- **Replay the stored transactions with FIFO on every read.** Rejected: hand-entered shares have no buy rows, so a sell of them has no cost, and a hand edit would silently change history. It would also need the holdings to reconcile with the transactions, which #28 does not require.
- **Average cost (what #28 shipped).** Rejected: the ticket asks for FIFO lots, and mixing average-cost holdings with FIFO realized P&L would make realized + unrealized disagree with the cash result.
- **A separate lots table.** Not needed yet: lots are only read and written with their holding, under the portfolio's row lock, so a JSONB column keeps one write path.

## Consequences

- Sells imported before this ADR have no booked P&L (`realized_pnl` NULL); their position and the portfolio total report `missing_data` with a reason.
- Realized P&L covers every imported sell to date, not only the analysis date range.
- Lots are not shown or editable yet. A user who needs exact lots edits nothing by hand and imports the full history.
- Realized P&L in a currency other than the reporting currency converts at each sell's date (ADR 0005, which superseded the earlier rule that left it out of the total).
