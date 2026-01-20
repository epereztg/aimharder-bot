# AimHarder Auto-Booking Bot

This Python application runs in GitHub Actions to automatically book classes on the AimHarder platform.

## Features

-   **Automated Booking**: Runs daily to book classes several days in advance.
-   **Schedule Based**: Uses per-box JSON schedule files (e.g., `schedule_10002.json`) to determine class times and names.
-   **Configurable Timing**: Wait times and target booking windows are configurable per box directly in the GitHub Actions workflow.
-   **WOD Fetching**: Automatically fetches and logs the Workout of the Day (WOD) for booked classes.

## Setup

1.  **Clone the repository**
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Each box is configured with its own schedule file and GitHub Actions workflow.

### 1. Schedule JSON (`schedule_XXXXX.json`)
Create a JSON file for your box (e.g., `schedule_10002.json`) with the following format:
```json
{
  "id": "10002",
  "name": "boxname",
  "Monday": { "time": "18:30", "class_name": "CrossFit" },
  "Friday": { "time": "17:30", "class_name": "Community WOD" },
  ...
}
```

### 2. GitHub Actions Workflow
Each box has its own workflow file in `.github/workflows/`. You can configure the specific booking opening time for each box using the `TARGET_HOUR` and `TARGET_MINUTE` variables:

```yaml
env:
  TARGET_HOUR: 18
  TARGET_MINUTE: 30
```

## Usage

### Local Execution
Set your credentials and runs the script targeting a specific schedule. By default, it will wait for the target time unless you use `--skip-wait`.

```bash
export EMAIL="your_email@gmail.com"
export PASSWORD="your_password"
python main.py --schedule schedule_10002.json
```

### Dry Run (Testing)
To test your configuration without actually booking a class, use the `--dry-run` flag. Combine it with `--skip-wait` and `--days-ahead 0` (for today) or `1` (for tomorrow) to see the matching logic in action:

```bash
python main.py --schedule schedule_10002.json --dry-run --skip-wait --days-ahead 0
```

### GitHub Actions
The bot runs automatically on the schedule defined in the `.yml` files.

**Required Secrets for Booking:**
- `EMAIL`: Your AimHarder login email.
- `PASSWORD`: Your AimHarder login password.

**Optional Secrets for Notifications:**
- `TELEGRAM_TOKEN`: Your Telegram Bot token (from [@BotFather](https://t.me/botfather)).
- `TELEGRAM_CHAT_ID`: Your personal Telegram Chat ID (from [@userinfobot](https://t.me/userinfobot)).

## Telegram Setup
1.  Message [@BotFather](https://t.me/botfather) to create a new bot and get your **API Token**.
2.  Message [@userinfobot](https://t.me/userinfobot) to find your **Chat ID**.
3.  Add both to your GitHub Repository Secrets (`Settings > Secrets and variables > Actions`).
4.  Once configured, the bot will send you a message every time it attempts a booking.
