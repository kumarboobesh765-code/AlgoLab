-- Enables TimescaleDB extension for time-series market data.
-- Hypertables for candles/ticks are created in Phase 2 (market data ingestion).
CREATE EXTENSION IF NOT EXISTS timescaledb;
