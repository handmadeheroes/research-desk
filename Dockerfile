FROM node:22-alpine AS ui
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-fund
COPY web ./web
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RD_DATA_DIR=/data
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml README.md ./
COPY research_desk ./research_desk
COPY --from=ui /build/research_desk/static/app.js ./research_desk/static/app.js
COPY --from=ui /build/research_desk/static/app.css ./research_desk/static/app.css
RUN pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home desk \
    && mkdir -p /data && chown desk:desk /data
USER desk
EXPOSE 8401
CMD ["sh","-c","research-desk init && exec research-desk serve --host 0.0.0.0"]
