FROM python:3.12-slim

WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# зависимости отдельным слоем: пока requirements.txt не менялся, слой берётся из кэша
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sla ./sla
COPY kit ./kit
COPY t05_orders_sla ./t05_orders_sla
COPY db ./db
COPY exchange ./exchange
COPY tests ./tests
COPY pytest.ini .flake8 ./

CMD ["python", "-m", "sla.cli", "pipeline"]
