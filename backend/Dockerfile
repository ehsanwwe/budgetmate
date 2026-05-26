FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Disable Debian repository validity check
RUN echo 'Acquire::Check-Valid-Until "false";' \
    > /etc/apt/apt.conf.d/99no-check-valid-until

# Replace default Debian sources with Abrha mirror
RUN rm -f /etc/apt/sources.list.d/debian.sources && \
    printf '%s\n' \
    'deb https://repo.abrha.net/debian trixie main contrib non-free non-free-firmware' \
    'deb https://repo.abrha.net/debian trixie-updates main contrib non-free non-free-firmware' \
    'deb https://repo.abrha.net/debian trixie-backports main contrib non-free non-free-firmware' \
    'deb https://repo.abrha.net/debian-security trixie-security main contrib non-free non-free-firmware' \
    > /etc/apt/sources.list

# Install system packages
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .

# Use Abrha PyPI mirror
RUN pip install --no-cache-dir \
    -i https://mirror.abrha.net/repository/pypi/simple \
    -r requirements.txt

COPY backend .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
