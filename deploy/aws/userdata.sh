#!/bin/bash
# Bedrock demo server: build the repo's own Dockerfile and run it on port 80 (reachable only through CloudFront).
exec > >(tee /var/log/bedrock-setup.log) 2>&1
set -eux
dnf install -y docker git
systemctl enable --now docker
# 1 GB swap as a safety net during the image build
fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
cd /opt
git clone https://github.com/ibnweb3/bedrock.git
cd bedrock
git log --oneline | head -1
for i in 1 2 3 4 5 6 7 8 9 10; do
  KEY=$(aws ssm get-parameter --name /bedrock/groq_api_key --with-decryption --region us-east-1 --query Parameter.Value --output text) && break
  sleep 10
done
docker build -t bedrock-demo .
docker run -d --name bedrock-live --restart unless-stopped \
  -e BEDROCK_PUBLIC=1 -e PORT=8765 -e GROQ_MODEL=openai/gpt-oss-120b -e GROQ_API_KEY="$KEY" \
  -p 80:8765 bedrock-demo
unset KEY
for i in $(seq 1 60); do curl -fs http://127.0.0.1/api/health && break; sleep 5; done
echo BEDROCK_SETUP_DONE
