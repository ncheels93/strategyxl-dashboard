-- =========================================================================
-- SQL Backtest Engine — Phase 1, Step 1
-- Create dbo.Scenario_Runs, dbo.Scenario_TradeLog, dbo.Scenario_Queue
-- =========================================================================
-- Idempotent: drops + recreates. Safe to re-run during dev.
-- For production, switch to CREATE OR ALTER pattern or guarded CREATE.
--
-- dbo.Scenario_TradeLog stores per-day engine output (~5K rows per run).
-- Persisted (rather than re-computed on demand) so the share-out site
-- (StrategyXL) can serve drill-in views as fast SELECTs against a
-- read-only mirror — no need to host the engine SP. At ~5K rows ×
-- ~25 cols × thousands of runs this stays in the single-digit-GB range.
-- =========================================================================

GO

-- Required for filtered indexes (sqlcmd default is OFF; SSMS default is ON)
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET NUMERIC_ROUNDABORT OFF;
GO

-- ===========================================================
-- Drop in FK-safe order: child tables (with FKs) before parent
-- ===========================================================
IF OBJECT_ID('dbo.Scenario_Queue', 'U') IS NOT NULL
    DROP TABLE dbo.Scenario_Queue;
GO

IF OBJECT_ID('dbo.Scenario_TradeLog', 'U') IS NOT NULL
    DROP TABLE dbo.Scenario_TradeLog;
GO

IF OBJECT_ID('dbo.Scenario_Runs', 'U') IS NOT NULL
    DROP TABLE dbo.Scenario_Runs;
GO

-- ===========================================================
-- dbo.Scenario_Runs — one row per logged scenario.
-- Single wide table: criteria (~30 in_* cols) + KPIs (~30 kpi_* cols).
-- run_id INT IDENTITY(1,1) starting at 1.
-- ===========================================================
CREATE TABLE dbo.Scenario_Runs (
    run_id              INT             IDENTITY(1,1) NOT NULL,
    run_timestamp       DATETIME2(0)    NOT NULL CONSTRAINT df_scenrun_ts DEFAULT SYSUTCDATETIME(),
    run_label           NVARCHAR(240)   NULL,
    batch_id            INT             NULL,
    queue_row_id        INT             NULL,

    -- ===== INPUTS =====
    -- Universe-defining (8)
    in_backtest_start           DATE            NULL,
    in_backtest_end             DATE            NULL,
    in_short_delta_threshold    DECIMAL(6,4)    NULL,
    in_short_delta_min          DECIMAL(6,4)    NULL,
    in_short_delta_max          DECIMAL(6,4)    NULL,
    in_spread_width             DECIMAL(8,2)    NULL,
    in_spread_handling          VARCHAR(20)     NULL,
    in_product_mode             VARCHAR(20)     NULL,

    -- Sizing
    in_starting_capital         DECIMAL(18,2)   NULL,
    in_base_trading_cap         DECIMAL(18,2)   NULL,
    in_upside_reinvest_pct      DECIMAL(6,4)    NULL,
    in_max_gross_pct_equity     DECIMAL(6,4)    NULL,
    in_gross_cap_activation_eq  DECIMAL(18,2)   NULL,

    -- Benchmark
    in_target_cagr              DECIMAL(6,4)    NULL,

    -- Trend filter
    in_trend_filter_on          BIT             NULL,
    in_trend_filter_ma          VARCHAR(20)     NULL,

    -- Exits
    in_breach_close             BIT             NULL,
    in_otm_close_threshold      DECIMAL(6,4)    NULL,
    in_profit_target            DECIMAL(6,4)    NULL,    -- NULL = OFF
    in_stop_loss                DECIMAL(6,4)    NULL,    -- NULL = OFF

    -- Costs
    in_commission_per_contract  DECIMAL(8,4)    NULL,
    in_slippage_per_leg         DECIMAL(8,4)    NULL,
    in_mid_source               VARCHAR(20)     NULL,
    in_entry_fill               VARCHAR(10)     NULL,
    in_exit_fill                VARCHAR(10)     NULL,

    -- Withdrawals
    in_withdrawals_on           BIT             NULL,
    in_target_monthly_withdrawal DECIMAL(18,2)  NULL,
    in_withdrawal_floor         DECIMAL(18,2)   NULL,
    in_withdrawal_start_date    DATE            NULL,
    in_inflation_adjust_pct     DECIMAL(6,4)    NULL,

    -- ===== OUTPUTS — Headline KPIs =====
    -- Precision: $ values stored at DECIMAL(18,4) (4dp), ratios at DECIMAL(10,8)
    -- (8dp). This matches Excel's FLOAT precision to within the validates
    -- thresholds ($0.01 / 0.0001). Without this, SQL's DECIMAL(18,2) rounding
    -- caused boundary-trigger DIFF on canonical scenarios (HANDOFF 2026-05-26).
    kpi_ending_equity           DECIMAL(18,4)   NULL,
    kpi_total_return_pct        DECIMAL(12,8)   NULL,
    kpi_years                   DECIMAL(8,4)    NULL,
    kpi_cagr                    DECIMAL(10,8)   NULL,
    kpi_realized_pnl            DECIMAL(18,4)   NULL,
    kpi_max_dd_pct              DECIMAL(10,8)   NULL,
    kpi_max_dd_date             DATE            NULL,
    kpi_calmar                  DECIMAL(18,8)   NULL,    -- widened (10,8)->(18,8): matches local
    kpi_total_trades            INT             NULL,
    kpi_win_rate                DECIMAL(10,8)   NULL,
    kpi_profit_factor           DECIMAL(18,8)   NULL,    -- widened: profit_factor up to ~118 overflowed (10,8)

    -- Friction (Block K — wired 2026-05-26)
    kpi_cum_commission          DECIMAL(18,4)   NULL,
    kpi_cum_slippage            DECIMAL(18,4)   NULL,

    -- Withdrawals
    kpi_total_withdrawn         DECIMAL(18,4)   NULL,
    kpi_coverage_pct            DECIMAL(10,8)   NULL,
    kpi_avg_monthly_income      DECIMAL(18,4)   NULL,
    kpi_worst_single_month      DECIMAL(18,4)   NULL,
    kpi_months_full             INT             NULL,
    kpi_months_partial          INT             NULL,
    kpi_months_zero             INT             NULL,
    kpi_months_not_started      INT             NULL,

    -- Benchmark drawdowns (NEW — Block J)
    kpi_max_dd_vs_start_pct     DECIMAL(10,8)   NULL,
    kpi_max_dd_vs_start_date    DATE            NULL,
    kpi_days_below_start        INT             NULL,
    kpi_pct_days_below_start    DECIMAL(10,8)   NULL,
    kpi_max_dd_vs_target_pct    DECIMAL(10,8)   NULL,
    kpi_max_dd_vs_target_date   DATE            NULL,
    kpi_days_below_target       INT             NULL,
    kpi_pct_days_below_target   DECIMAL(10,8)   NULL,

    -- Risk-adjusted metrics (monthly returns, FRED risk-free, Sortino MAR=0, annualized ×√12)
    -- Widened (10,8)->(18,8) to match local — the narrow type overflowed on large ratios.
    kpi_ann_return_stdev        DECIMAL(18,8)   NULL,
    kpi_sharpe                  DECIMAL(18,8)   NULL,
    kpi_sortino                 DECIMAL(18,8)   NULL,

    -- Capped sizing model (in_sizing_mode='capped' → weekly $ = MIN(weekly_risk_pct×equity, cap))
    in_sizing_mode              VARCHAR(10)     NULL,
    in_weekly_risk_pct          DECIMAL(6,4)    NULL,
    in_max_weekly_risk          DECIMAL(18,2)   NULL,    -- NULL = uncapped

    -- Win/loss profile KPIs (the "small wins, occasional big loss" shape)
    kpi_avg_win                 DECIMAL(18,2)   NULL,
    kpi_avg_loss                DECIMAL(18,2)   NULL,
    kpi_biggest_loss            DECIMAL(18,2)   NULL,
    kpi_win_loss_ratio          DECIMAL(18,8)   NULL,

    -- Money-weighted return + total-value return (XIRR block — _sql_38)
    kpi_xirr                    DECIMAL(18,8)   NULL,
    kpi_total_value_return      DECIMAL(12,8)   NULL,

    CONSTRAINT pk_scenario_runs PRIMARY KEY CLUSTERED (run_id)
);
GO

CREATE NONCLUSTERED INDEX ix_scenario_calmar  ON dbo.Scenario_Runs (kpi_calmar DESC);
CREATE NONCLUSTERED INDEX ix_scenario_cagr    ON dbo.Scenario_Runs (kpi_cagr DESC);
CREATE NONCLUSTERED INDEX ix_scenario_max_dd  ON dbo.Scenario_Runs (kpi_max_dd_pct DESC);
CREATE NONCLUSTERED INDEX ix_scenario_batch   ON dbo.Scenario_Runs (batch_id, run_id);
GO

-- ===========================================================
-- dbo.Scenario_TradeLog — per-day engine output, one row per
-- (run_id, day_num). Persisted at run time by the wrapper SP
-- (Phase 1.1) so the share-out site can drill in via fast SELECT.
--
-- Column set mirrors Excel's tbl_TradeLog (80 cols, blocks A-K)
-- EXCEPT for 5 Excel-internal lookup-row indices that have no
-- semantic meaning in SQL:
--    Short_Row, Long_Row, Entry_Short_Row, Entry_Long_Row, DoW
-- Result: 75 data cols + run_id.
--
-- Column names match Excel column names lowercased (date → trade_date
-- to avoid the SQL keyword collision; everything else is a direct map).
-- ===========================================================
-- NOT NULL policy (set 2026-05-26): fail-fast on the path-dependent state and
-- always-emitted cols. Cols that legitimately carry NULL ("no trade today",
-- "no exit event", "MA window not yet filled", "ORATS data gap") stay nullable.
-- See section 5o of HANDOFF.md for the rationale.
CREATE TABLE dbo.Scenario_TradeLog (
    run_id                          INT             NOT NULL,

    -- ===== Block A: DATE & MARKET =====
    day_num                         INT             NOT NULL,
    trade_date                      DATE            NOT NULL,     -- Excel: Date
    spx_close                       DECIMAL(18,4)   NOT NULL,
    trend_ma                        DECIMAL(18,4)   NULL,         -- NULL for early dates (e.g. sma_200 first 200 days)
    above_trend                     BIT             NOT NULL,     -- CASE evaluates 0 when trend_ma is NULL

    -- ===== Block B: ENTRY DETECTION =====
    is_friday                       BIT             NOT NULL,
    holiday_thursday                BIT             NOT NULL,
    entry_day                       BIT             NOT NULL,
    filter_pass                     BIT             NOT NULL,

    -- ===== Block C: TRADE STATE =====
    trade_num                       INT             NULL,         -- NULL when trend filter rejects entry that week

    -- ===== Block D: DAILY OPTION DATA (NULL when no trade in flight OR ORATS data gap) =====
    entry_date                      DATE            NULL,
    expir_date                      DATE            NULL,
    product                         VARCHAR(10)     NULL,
    settlement                      VARCHAR(10)     NULL,
    short_strike                    DECIMAL(12,4)   NULL,
    long_strike                     DECIMAL(12,4)   NULL,
    dte_remaining                   INT             NULL,
    days_since_entry                INT             NULL,
    short_pbid                      DECIMAL(12,4)   NULL,
    short_pask                      DECIMAL(12,4)   NULL,
    short_mid                       DECIMAL(12,4)   NULL,
    short_pvolu                     INT             NULL,
    short_poi                       INT             NULL,
    short_delta                     DECIMAL(10,6)   NULL,
    long_pbid                       DECIMAL(12,4)   NULL,
    long_pask                       DECIMAL(12,4)   NULL,
    long_mid                        DECIMAL(12,4)   NULL,
    long_pvolu                      INT             NULL,
    long_poi                        INT             NULL,
    long_delta                      DECIMAL(10,6)   NULL,
    spread_cost_to_close            DECIMAL(12,4)   NULL,

    -- ===== Block E: ENTRY REFS & SIZING =====
    entry_short_mid                 DECIMAL(12,4)   NULL,         -- NULL on no-trade days
    entry_long_mid                  DECIMAL(12,4)   NULL,
    entry_credit_per_spread         DECIMAL(12,4)   NULL,
    spread_width_actual             DECIMAL(12,4)   NULL,
    trading_cap                     DECIMAL(18,4)   NOT NULL,     -- always derived from prior equity
    contracts                       INT             NULL,         -- NULL or 0 on no-trade days
    credit_total                    DECIMAL(18,2)   NULL,
    gross_exposure_total            DECIMAL(18,2)   NULL,
    max_loss                        DECIMAL(18,2)   NULL,

    -- ===== Block F: UNREALIZED P&L (all NULL on no-trade days) =====
    unrealized_pnl_per_share        DECIMAL(12,4)   NULL,
    unrealized_pnl_total            DECIMAL(18,2)   NULL,
    pct_of_max_profit               DECIMAL(8,4)    NULL,
    pct_otm_vs_short                DECIMAL(8,4)    NULL,

    -- ===== Block G: REALIZED P&L (event-day-only cols are NULL; the always-emitted ones are NOT NULL) =====
    exit_reason                     VARCHAR(20)     NULL,
    exit_cost_per_share             DECIMAL(12,4)   NULL,
    realized_pnl_per_share          DECIMAL(12,4)   NULL,
    realized_pnl_total              DECIMAL(18,2)   NULL,
    expiring_trade_num              INT             NULL,
    expir_realized_pnl_per_share    DECIMAL(12,4)   NULL,
    expir_realized_pnl_total        DECIMAL(18,2)   NULL,
    realized_pnl_today              DECIMAL(18,4)   NOT NULL,     -- 0 on no-realization days
    cum_realized_pnl                DECIMAL(18,4)   NOT NULL,

    -- ===== Block H: CASH & EQUITY =====
    credit_in_today                 DECIMAL(18,2)   NOT NULL,     -- 0 when no entry
    early_exit_cost_today           DECIMAL(18,2)   NOT NULL,     -- 0 when no early exit
    expir_cost_today                DECIMAL(18,2)   NOT NULL,     -- 0 when no expir
    rate_pct_today                  DECIMAL(8,4)    NOT NULL,     -- ISNULL-wrapped in #spine
    cash_eod                        DECIMAL(18,4)   NOT NULL,
    interest_today                  DECIMAL(18,4)   NOT NULL,
    trade_closed_by_eod             INT             NOT NULL,     -- 0 or 1
    mtm_eod                         DECIMAL(18,4)   NOT NULL,
    equity_eod                      DECIMAL(18,4)   NOT NULL,
    peak_equity                     DECIMAL(18,4)   NOT NULL,
    drawdown_pct                    DECIMAL(8,4)    NULL,         -- CAST returns NULL if peak_equity=0 (degenerate)

    -- ===== Block I: WITHDRAWALS =====
    target_withdrawal_today         DECIMAL(18,4)   NOT NULL,     -- 0 when off / pre-start / non-event day
    withdrawal_today                DECIMAL(18,4)   NOT NULL,
    withdrawal_status               VARCHAR(20)     NULL,         -- NULL on non-event days
    cum_withdrawn                   DECIMAL(18,4)   NOT NULL,

    -- ===== Block J: BENCHMARK DRAWDOWNS =====
    dd_vs_starting_pct              DECIMAL(8,4)    NOT NULL,     -- CASE returns 0 when above starting
    target_equity_cagr              DECIMAL(18,4)   NOT NULL,
    dd_vs_target_cagr_pct           DECIMAL(8,4)    NULL,         -- NULL when target_equity_cagr <= 0 (with withdrawals)

    -- ===== Block K: FRICTION =====
    commission_today                DECIMAL(18,4)   NOT NULL,
    slippage_today                  DECIMAL(18,4)   NOT NULL,
    cum_commission                  DECIMAL(18,4)   NOT NULL,
    cum_slippage                    DECIMAL(18,4)   NOT NULL,

    CONSTRAINT pk_scenario_tradelog PRIMARY KEY CLUSTERED (run_id, day_num),
    CONSTRAINT fk_scenario_tradelog_run
        FOREIGN KEY (run_id) REFERENCES dbo.Scenario_Runs (run_id) ON DELETE CASCADE
);
GO

-- Secondary index for date-range queries within a run (chart paging etc.)
CREATE NONCLUSTERED INDEX ix_tradelog_run_date ON dbo.Scenario_TradeLog (run_id, trade_date);
GO

-- ===========================================================
-- dbo.Scenario_Queue — staging table (Excel-linked).
-- User populates the in_* cols; batch driver pops pending rows.
-- ===========================================================
CREATE TABLE dbo.Scenario_Queue (
    queue_row_id        INT             IDENTITY(1,1) NOT NULL,
    batch_id            INT             NOT NULL,
    queue_label         NVARCHAR(240)   NULL,
    queued_timestamp    DATETIME2(0)    NOT NULL CONSTRAINT df_scenq_ts DEFAULT SYSUTCDATETIME(),
    status              VARCHAR(20)     NOT NULL CONSTRAINT df_scenq_status DEFAULT 'pending',
                        -- pending | running | complete | error
    started_at          DATETIME2(0)    NULL,
    completed_at        DATETIME2(0)    NULL,
    run_id              INT             NULL,
    error_msg           NVARCHAR(2000)  NULL,

    -- ===== Same ~30 in_* cols as Scenario_Runs =====
    in_backtest_start           DATE            NULL,
    in_backtest_end             DATE            NULL,
    in_short_delta_threshold    DECIMAL(6,4)    NULL,
    in_short_delta_min          DECIMAL(6,4)    NULL,
    in_short_delta_max          DECIMAL(6,4)    NULL,
    in_spread_width             DECIMAL(8,2)    NULL,
    in_spread_handling          VARCHAR(20)     NULL,
    in_product_mode             VARCHAR(20)     NULL,
    in_starting_capital         DECIMAL(18,2)   NULL,
    in_base_trading_cap         DECIMAL(18,2)   NULL,
    in_upside_reinvest_pct      DECIMAL(6,4)    NULL,
    in_max_gross_pct_equity     DECIMAL(6,4)    NULL,
    in_gross_cap_activation_eq  DECIMAL(18,2)   NULL,
    in_target_cagr              DECIMAL(6,4)    NULL,
    in_trend_filter_on          BIT             NULL,
    in_trend_filter_ma          VARCHAR(20)     NULL,
    in_breach_close             BIT             NULL,
    in_otm_close_threshold      DECIMAL(6,4)    NULL,
    in_profit_target            DECIMAL(6,4)    NULL,
    in_stop_loss                DECIMAL(6,4)    NULL,
    in_commission_per_contract  DECIMAL(8,4)    NULL,
    in_slippage_per_leg         DECIMAL(8,4)    NULL,
    in_mid_source               VARCHAR(20)     NULL,
    in_entry_fill               VARCHAR(10)     NULL,
    in_exit_fill                VARCHAR(10)     NULL,
    in_withdrawals_on           BIT             NULL,
    in_target_monthly_withdrawal DECIMAL(18,2)  NULL,
    in_withdrawal_floor         DECIMAL(18,2)   NULL,
    in_withdrawal_start_date    DATE            NULL,
    in_inflation_adjust_pct     DECIMAL(6,4)    NULL,

    CONSTRAINT pk_scenario_queue PRIMARY KEY CLUSTERED (queue_row_id),
    CONSTRAINT ck_scenq_status   CHECK (status IN ('pending','running','complete','error'))
);
GO

-- Filtered index on pending rows — keeps the batch-driver cursor fast even
-- when the queue accumulates lots of complete rows over time.
CREATE NONCLUSTERED INDEX ix_queue_pending ON dbo.Scenario_Queue (batch_id, queue_row_id)
    WHERE status = 'pending';
GO

DECLARE @runs_cols INT, @tlog_cols INT, @queue_cols INT;
SELECT @runs_cols  = COUNT(*) FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Scenario_Runs');
SELECT @tlog_cols  = COUNT(*) FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Scenario_TradeLog');
SELECT @queue_cols = COUNT(*) FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Scenario_Queue');
PRINT 'Created dbo.Scenario_Runs      (' + CAST(@runs_cols  AS VARCHAR) + ' cols)';
PRINT 'Created dbo.Scenario_TradeLog  (' + CAST(@tlog_cols  AS VARCHAR) + ' cols)';
PRINT 'Created dbo.Scenario_Queue     (' + CAST(@queue_cols AS VARCHAR) + ' cols)';
GO

-- ===========================================================
-- dbo.SPX_Daily_MAs — SPX daily close + all moving averages.
-- Holds the 2007+ subset on the share DB (full history lives on StockDevVM).
-- Run-independent reference data used by the dashboard for per-trade entry
-- context (% above 200-day SMA, etc.). GUARDED create (NOT drop+recreate) so
-- a full re-run of this script never wipes the migrated daily series.
-- ===========================================================
IF OBJECT_ID('dbo.SPX_Daily_MAs', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.SPX_Daily_MAs (
        trade_date  DATE            NOT NULL,
        spx_close   DECIMAL(18,6)   NOT NULL,
        sma_5       DECIMAL(18,6)   NULL,
        sma_10      DECIMAL(18,6)   NULL,
        sma_20      DECIMAL(18,6)   NULL,
        sma_50      DECIMAL(18,6)   NULL,
        sma_100     DECIMAL(18,6)   NULL,
        sma_150     DECIMAL(18,6)   NULL,
        sma_200     DECIMAL(18,6)   NULL,
        ema_9       DECIMAL(18,6)   NULL,
        ema_20      DECIMAL(18,6)   NULL,
        ema_50      DECIMAL(18,6)   NULL,
        ema_200     DECIMAL(18,6)   NULL,
        CONSTRAINT pk_spx_daily_mas PRIMARY KEY CLUSTERED (trade_date)
    );
    PRINT 'Created dbo.SPX_Daily_MAs';
END
ELSE
    PRINT 'dbo.SPX_Daily_MAs already exists — left as-is.';
GO

-- ===========================================================
-- dbo.Scenario_Requests — Request-a-Run submissions. The dashboard WRITES here
-- (everything else it only reads). GUARDED create (NOT drop+recreate): this holds
-- user-submitted requests, so re-running this script must never wipe them. The app
-- reads/writes by column NAME, so this column order is independent of other tables.
-- ===========================================================
IF OBJECT_ID('dbo.Scenario_Requests', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Scenario_Requests (
        request_id          INT IDENTITY(1,1) NOT NULL,
        requested_at        DATETIME2       NOT NULL CONSTRAINT df_screq_at DEFAULT SYSDATETIME(),
        requested_by        NVARCHAR(100)   NULL,
        scenario_name       NVARCHAR(200)   NOT NULL,
        status              VARCHAR(20)     NOT NULL CONSTRAINT df_screq_status DEFAULT 'Pending',
        result_queue_name   NVARCHAR(300)   NULL,
        notes               NVARCHAR(500)   NULL,
        in_spread_width              DECIMAL(8,2)  NOT NULL,
        in_trend_filter_on           BIT           NOT NULL,
        in_trend_filter_ma           VARCHAR(20)   NULL,
        in_weekly_risk_pct           DECIMAL(6,4)  NOT NULL,
        in_max_weekly_risk           DECIMAL(18,2) NULL,
        in_withdrawals_on            BIT           NOT NULL,
        in_target_monthly_withdrawal DECIMAL(18,2) NULL,
        in_withdrawal_floor          DECIMAL(18,2) NULL,
        in_starting_capital          DECIMAL(18,2) NOT NULL,
        in_short_delta_threshold     DECIMAL(6,4)  NOT NULL,
        in_commission_per_contract   DECIMAL(8,4)  NOT NULL,
        in_slippage_per_leg          DECIMAL(8,4)  NOT NULL,
        in_otm_close_threshold       DECIMAL(6,4)  NULL,
        in_breach_close              BIT           NOT NULL,
        in_profit_target             DECIMAL(6,4)  NULL,
        in_stop_loss                 DECIMAL(6,4)  NULL,
        in_backtest_start            DATE          NOT NULL,
        in_backtest_end              DATE          NOT NULL,
        in_inflation_adjust_pct      DECIMAL(6,4)  NULL,
        CONSTRAINT pk_scenario_requests PRIMARY KEY CLUSTERED (request_id)
    );
    PRINT 'Created dbo.Scenario_Requests';
END
ELSE
    PRINT 'dbo.Scenario_Requests already exists — left as-is (requests preserved).';
GO

-- WRITE GRANT — the app needs INSERT/UPDATE/DELETE on this one table (it only reads
-- the rest). Grant to whatever login the dashboard's [database] secret connects as.
-- If that login is the server admin 'sqladmin', it already has full rights and no
-- grant is needed. Uncomment + set the login before running if it's a separate user:
-- GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.Scenario_Requests TO [<APP_DB_LOGIN>];
-- GO
