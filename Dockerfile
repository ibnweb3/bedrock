# Bedrock: FalkorDB + the audit web app in one container (used for the public demo and for judges).
# Base image = the same FalkorDB build used in development, pinned by digest (tag: falkordb/falkordb:latest, 2026-10-15).
FROM falkordb/falkordb@sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/venv \
 && echo "bedrock:x:10001:10001::/home/bedrock:/usr/sbin/nologin" >> /etc/passwd \
 && echo "bedrock:x:10001:" >> /etc/group \
 && mkdir -p /home/bedrock && chown 10001:10001 /home/bedrock

ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 BEDROCK_PUBLIC=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

WORKDIR /app
COPY src /app/src
COPY queries /app/queries
COPY scripts/serve.py scripts/snapshot.py /app/scripts/
COPY deploy /app/deploy
RUN chmod +x /app/deploy/entrypoint.sh

USER bedrock
# The graph snapshot is restored at start-up from /app/deploy (see docs/DEPLOY.md). GROQ_API_KEY is optional:
# without it the app still works as a plain graph audit.
EXPOSE 8765
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
