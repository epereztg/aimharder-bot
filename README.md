# AimHarder Auto-Booking Bot

This Python application runs in GitHub Actions to automatically book CrossFit classes on AimHarder (specifically for WeZone Arturo Soria).

## Features

- **Automated Booking**: Runs daily to book classes 2 days in advance.
- **Schedule Based**: Uses a `schedule_10002.json` file to determine which class to book based on the day of the week.
- **Configurable**: Supports customizable box names and IDs via environment variables or command-line arguments.

## Setup

1.  **Clone the repository**
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Local Execution

You can run the script locally by setting the required environment variables:

```bash
export EMAIL="your_email@example.com"
export PASSWORD="your_password"
python main.py
```

### GitHub Actions

The workflow is configured in `.github/workflows/book_class.yml`. It runs daily at 5:45 AM UTC (targeting 7:00 AM Madrid time).

**Required Secrets:**

- `EMAIL`: Your AimHarder account email.
- `PASSWORD`: Your AimHarder account password.

**Inputs/Variables:**

- `BOX_NAME`: Default is `wezonearturosoria`.
- `BOX_ID`: Default is `10584`.
