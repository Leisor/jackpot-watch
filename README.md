# Veikkaus Jackpot Watcher

Checks Veikkaus jackpot amounts and sends notifications when they reach certain thresholds.

## Games Monitored

| Game | Check Days | Time |
|------|------------|------|
| LOTTO | Sunday | 09:00 |
| EUROJACKPOT | Wednesday, Saturday | 18:50 |
| VIKINGLOTTO | Thursday | 18:50 |

## Setup

1. Build and run with Docker:
   ```bash
   docker-compose up -d
   ```

2. Configure Telegram notifications via environment variables (see `docker-compose.yml`).

## Environment Variables

- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `TELEGRAM_CHAT_ID` - Telegram chat ID to send notifications
- `CRON_SUN_HOUR` - Hour for Lotto check (default: 9)
- `CRON_WED_HOUR` - Hour for Eurojackpot Wed check (default: 18)
- `CRON_THU_HOUR` - Hour for Vikinglotto check (default: 18)
- `JACKPOT_THRESHOLD_LOTTO` - Lotto jackpot threshold (default: 5.5M €)
- `JACKPOT_THRESHOLD_EUROJACKPOT` - Eurojackpot threshold (default: 80M €)
- `JACKPOT_THRESHOLD_VIKINGLOTTO` - Vikinglotto threshold (default: 18M €)
