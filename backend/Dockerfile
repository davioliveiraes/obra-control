FROM python:3.14.7-slim-bookworm AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system django \
    && adduser --system --ingroup django django

COPY requirements/base.txt requirements/base.txt
RUN python -m pip install --no-cache-dir -r requirements/base.txt

FROM dependencies AS development

COPY requirements/dev.txt requirements/dev.txt
RUN python -m pip install --no-cache-dir -r requirements/dev.txt \
    && mkdir -p /workspace/backend \
    && chown -R django:django /workspace

WORKDIR /workspace/backend
COPY --chown=django:django . .
WORKDIR /workspace
USER django
CMD ["python", "backend/manage.py", "runserver", "0.0.0.0:8000"]

FROM dependencies AS runtime

COPY --chown=django:django . .

USER django

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
