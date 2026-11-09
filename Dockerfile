FROM python:3.11-slim

WORKDIR /srv

# Dependencies first so a code-only change keeps this layer cached.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

RUN useradd --system --uid 10001 obs
USER obs

# No secrets here: pass OBSKIT_PLATFORM_DATABASE_URL and OBSKIT_PLATFORM_API_KEY
# with `docker run -e ...` (or compose). Migrations are a separate step: `alembic upgrade head`.
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
