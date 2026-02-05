# Uses Ubuntu Jammy with Playwright v1.46.0 + browsers preinstalled
FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

WORKDIR /app
COPY requirements.txt .
# playwright is already present in the base image; this won't reinstall browsers
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Default envs (override at runtime)
ENV TIMEZONE=Europe/Helsinki \
    CRON_SUN_HOUR=9 \
    CRON_WED_HOUR=9 \
    RUN_ONCE=0

CMD ["python", "main.py"]
