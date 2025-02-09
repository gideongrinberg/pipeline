FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential

# Install poetry
# RUN curl -sSL https://install.python-poetry.org | python3 -
# RUN ln -s /root/.local/bin/poetry /usr/local/bin/poetry
# ENV PATH="/root/.local/bin:$PATH"
ENV POETRY_HOME=/opt/poetry
RUN python3 -m venv ${POETRY_HOME} \
        && ${POETRY_HOME}/bin/pip install poetry

WORKDIR /app

# Install packages
COPY pyproject.toml poetry.lock* ./
RUN ${POETRY_HOME}/bin/poetry config virtualenvs.create false \
    && ${POETRY_HOME}/bin/poetry install --no-interaction --no-ansi

COPY . .
CMD ["python", "chunked.py", "tics.txt"]