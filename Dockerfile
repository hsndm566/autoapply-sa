# Dockerfile — runs n8n (pre-built official image) + imports AutoApply workflows
# + runs the gated email sender as a background process.
FROM n8nio/n8n:latest

USER root
WORKDIR /home/node/.n8n

# copy workflows + sender code
COPY workflows /workflows
COPY autoapply-sent-log.csv /home/node/.n8n/autoapply-sent-log.csv
COPY push_pool.csv /home/node/.n8n/push_pool.csv
COPY cv_variants /home/node/.n8n/cv_variants
COPY night_send_safe.py /home/node/.n8n/night_send_safe.py
COPY quality_gate.py /home/node/.n8n/quality_gate.py
COPY self_heal.py /home/node/.n8n/self_heal.py
COPY telegram_counter.py /home/node/.n8n/telegram_counter.py
COPY cloud_loop.py /home/node/.n8n/cloud_loop.py
COPY verify_cv.py /home/node/.n8n/verify_cv.py
COPY email_industry_map.json /home/node/.n8n/email_industry_map.json

# install python + deps for the sender
RUN apt-get update && apt-get install -y python3 python3-pip && \
    pip3 install --break-system-packages pymupdf pypdf pdfplumber reportlab || \
    pip3 install pymupdf pypdf pdfplumber reportlab

COPY docker-start.sh /home/node/.n8n/docker-start.sh
RUN chmod +x /home/node/.n8n/docker-start.sh

EXPOSE 5678
USER node
CMD ["/home/node/.n8n/docker-start.sh"]
